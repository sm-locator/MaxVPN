#!/usr/bin/env bash
set -Eeuo pipefail

# MaxVPN Smart Routing IPv4 diagnostics.
# READ-ONLY: this script does not modify routes, firewall, ipsets, VPN settings,
# or iptables counters. tcpdump runs interactively and does not write a pcap.

ROUTER="${MAXVPN_ROUTER:-root@192.168.8.1}"
LAN_CLIENT_IP="${MAXVPN_LAN_CLIENT_IP:-}"
MODE="${1:-}"
if [[ -n "$MODE" ]]; then shift; fi

usage() {
  cat <<'USAGE'
MaxVPN Smart Routing — read-only IPv4 diagnostics

Usage:
  maxvpn_smart_routing_ipv4.sh audit domain.example [domain.example ...]
  maxvpn_smart_routing_ipv4.sh capture domain.example

Modes:
  audit    Check DNS A records, DIRECT ipsets, mangle rules, fwmark policy,
           and route table 200. No packet capture is started.
  capture  Resolve one domain through the router, verify its first IPv4 A record
           is in MAXVPN_DIRECT and has the expected marked route, then run an
           interactive tcpdump on eth1 until you press Ctrl+C. No time window.

Environment:
  MAXVPN_ROUTER=root@192.168.8.1  Override SSH destination.
  MAXVPN_LAN_CLIENT_IP=192.168.8.X  Optional real LAN client IPv4 for a source-aware
                                  simulated ingress route lookup.

IPv6 is N/A because this ISP does not provide IPv6. The script never enables
IPv6 or changes runtime configuration. No iptables/ipset counters are reset.
USAGE
}

if [[ "$MODE" == "-h" || "$MODE" == "--help" || -z "$MODE" ]]; then usage; exit 0; fi
if [[ "$MODE" != "audit" && "$MODE" != "capture" ]]; then
  printf 'Unknown mode: %s\n\n' "$MODE" >&2
  usage >&2
  exit 2
fi
if (($# == 0)); then usage >&2; exit 2; fi
if [[ "$MODE" == "capture" && $# -ne 1 ]]; then
  echo 'capture mode accepts exactly one domain.' >&2
  usage >&2
  exit 2
fi

DOMAINS=()
for raw in "$@"; do
  domain="${raw,,}"
  domain="${domain%.}"
  if [[ ! "$domain" =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; then
    printf 'Invalid domain name: %s\n' "$raw" >&2
    exit 2
  fi
  DOMAINS+=("$domain")
done

if [[ "$MODE" == "audit" ]]; then
  echo "Connecting to ${ROUTER}..."
  if [[ -n "$LAN_CLIENT_IP" && ! "$LAN_CLIENT_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
    echo "MAXVPN_LAN_CLIENT_IP must be a dotted IPv4 address (or omitted)." >&2
    exit 2
  fi
  ssh "$ROUTER" python3 - "${LAN_CLIENT_IP:-N/A}" "${DOMAINS[@]}" <<'PY'
import ipaddress
import re
import subprocess
import sys

LAN_CLIENT_IP = sys.argv[1]
LAN_CLIENT_IP = None if LAN_CLIENT_IP == "N/A" else LAN_CLIENT_IP
DOMAINS = sys.argv[2:]
DIRECT_SET = "MAXVPN_DIRECT"
STATIC_SET = "MAXVPN_DIRECT_STATIC"
MARK = "0x64"
TABLE = "200"
failures = 0
warnings = 0


def note(status, label, detail=""):
    global failures, warnings
    print(f"[{status}] {label}" + (f": {detail}" if detail else ""), flush=True)
    if status == "FAIL":
        failures += 1
    elif status == "WARN":
        warnings += 1


def run(args, timeout=10):
    try:
        proc = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except Exception as exc:
        return 127, "", str(exc)


def ipset_info(name):
    rc, out, err = run(["ipset", "list", name])
    if rc:
        return None, err.strip() or out.strip() or f"exit code {rc}"
    count_match = re.search(r"^Number of entries:\s*(\d+)", out, re.M)
    members = set()
    in_members = False
    for line in out.splitlines():
        token = line.strip()
        if token == "Members:":
            in_members = True
            continue
        if not in_members or not token:
            continue
        try:
            addr = ipaddress.ip_address(token)
        except ValueError:
            continue
        if addr.version == 4:
            members.add(str(addr))
    return {"count": int(count_match.group(1)) if count_match else len(members), "members": members}, ""


def resolve_a(domain):
    rc, out, err = run(["nslookup", domain, "127.0.0.1"])
    candidates = []
    lines = out.splitlines()
    name_indexes = [i for i, line in enumerate(lines) if re.match(r"^\s*Name\s*:", line, re.I)]
    if name_indexes:
        for line in lines[name_indexes[0] + 1:]:
            candidates.extend(re.findall(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])", line))
    else:
        for line in lines:
            if re.search(r"\bAddress\s*\d*\s*:", line, re.I) and re.search(re.escape(domain), line, re.I):
                candidates.extend(re.findall(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])", line))
    addresses = []
    for value in candidates:
        try:
            addr = ipaddress.ip_address(value)
        except ValueError:
            continue
        if addr.version == 4 and not addr.is_loopback and not addr.is_unspecified and not addr.is_multicast:
            addresses.append(str(addr))
    return rc, list(dict.fromkeys(addresses)), out.strip(), err.strip()


def counter_for_direct():
    rc, out, err = run(["iptables", "-t", "mangle", "-L", "PREROUTING", "-nvx", "--line-numbers"])
    if rc:
        return None, None, err.strip() or out.strip() or f"exit code {rc}"
    for line in out.splitlines():
        lowered = line.lower()
        if "match-set maxvpn_direct dst" not in lowered or "0x64/0xff" not in lowered or "mark" not in lowered:
            continue
        match = re.match(r"^\s*\d+\s+(\d+)\s+(\d+)\s+", line)
        if match:
            return int(match.group(1)), int(match.group(2)), ""
    return None, None, "could not locate dynamic DIRECT counter in PREROUTING"


def has_mark_rule(lines, set_name):
    return any(set_name.lower() in line.lower() and "0x64/0xff" in line.lower() and "MARK" in line.upper() for line in lines)


print("\nMaxVPN Smart Routing — IPv4 audit (read-only)", flush=True)
print("Router: OpenWrt via SSH", flush=True)
print(f"Domains: {', '.join(DOMAINS)}", flush=True)
print("IPv6: N/A — провайдер не предоставляет IPv6; IPv6 не проверяется и не изменяется.", flush=True)
print("No routes, rules, ipsets, VPN settings, or counters will be changed/reset.", flush=True)

print("\n== Runtime prerequisites ==", flush=True)
direct_info, direct_err = ipset_info(DIRECT_SET)
static_info, static_err = ipset_info(STATIC_SET)
note("PASS" if direct_info is not None else "FAIL", f"IPv4 ipset {DIRECT_SET} exists/readable", f"entries={direct_info['count']}" if direct_info else direct_err)
note("PASS" if static_info is not None else "FAIL", f"IPv4 ipset {STATIC_SET} exists/readable", f"entries={static_info['count']} (empty is valid)" if static_info else static_err)

rc, rules_out, rules_err = run(["ip", "-4", "rule", "show"])
policy = next((line.strip() for line in rules_out.splitlines() if "fwmark 0x64/0xff" in line.lower() and re.search(r"lookup\s+200\b", line)), None)
note("PASS" if rc == 0 and policy else "FAIL", "fwmark policy routes 0x64/0xff to table 200", policy or (rules_err.strip() or rules_out.strip() or f"exit code {rc}"))

rc, mangle_out, mangle_err = run(["iptables", "-t", "mangle", "-S"])
mlines = mangle_out.splitlines()
for set_name, label in ((DIRECT_SET, "dynamic DIRECT"), (STATIC_SET, "static DIRECT")):
    matched = rc == 0 and has_mark_rule(mlines, set_name)
    note("PASS" if matched else "FAIL", f"mangle rule covers {label} with mark 0x64", "matching rule found" if matched else (mangle_err.strip() or "no matching rule found"))

rc, table_out, table_err = run(["ip", "-4", "route", "show", "table", TABLE])
wan_default = next((line.strip() for line in table_out.splitlines() if re.match(r"^default\b", line.strip()) and re.search(r"\bdev\s+eth1\b", line)), None)
note("PASS" if rc == 0 and wan_default else "FAIL", "table 200 has an IPv4 default route via WAN eth1", wan_default or (table_err.strip() or table_out.strip() or f"exit code {rc}"))

counter, counter_bytes, counter_error = counter_for_direct()
if counter is None:
    note("WARN", "read MAXVPN_DIRECT mangle counter", counter_error)
else:
    note("INFO", "MAXVPN_DIRECT PREROUTING counter", f"packets={counter}, bytes={counter_bytes}; shared counter, not domain-specific")

print("\n== Per-domain checks (DNS A records only) ==", flush=True)
for domain in DOMAINS:
    print(f"\n-- {domain} --", flush=True)
    rc, addresses, dns_out, dns_err = resolve_a(domain)
    if rc != 0 or not addresses:
        note("FAIL", f"DNS A record for {domain} via router resolver", dns_err or dns_out or f"resolver exit code {rc}; no IPv4 A record found")
        continue
    note("PASS", f"DNS A record for {domain} via router resolver", ", ".join(addresses))
    for address in addresses:
        if direct_info is None:
            present, detail = False, "ipset unreadable"
        else:
            test_rc, _, test_err = run(["ipset", "test", DIRECT_SET, address])
            present = test_rc == 0
            detail = f"present in {DIRECT_SET}" if present else (test_err.strip() or f"not present in {DIRECT_SET}")
        note("PASS" if present else "FAIL", f"{address} belongs to {DIRECT_SET}", detail)
        route_rc, route_out, route_err = run(["ip", "-4", "route", "get", address, "mark", MARK])
        normalized = " ".join(route_out.split())
        route_ok = route_rc == 0 and re.search(r"\btable\s+200\b", normalized) and re.search(r"\bmark\s+0x64\b", normalized.lower()) and re.search(r"\bdev\s+eth1\b", normalized)
        note("PASS" if route_ok else "FAIL", f"marked route for {address} uses table 200 via eth1", normalized or route_err.strip() or f"exit code {route_rc}")
        # An ingress route lookup is only meaningful with the real source IP of
        # a LAN client. The previous source-less `... iif br-lan` probe returned
        # EINVAL on this OpenWrt runtime. Keep this auxiliary check non-blocking.
        if not LAN_CLIENT_IP:
            note("INFO", f"source-aware unmarked LAN lookup for {address}",
                 "N/A: set MAXVPN_LAN_CLIENT_IP to a real LAN client's IPv4 address; not required for DIRECT/WAN verification")
        else:
            try:
                lan_source = ipaddress.ip_address(LAN_CLIENT_IP)
            except ValueError:
                lan_source = None
            if lan_source is None or lan_source.version != 4 or lan_source.is_loopback or lan_source.is_unspecified or lan_source.is_multicast:
                note("INFO", f"source-aware unmarked LAN lookup for {address}",
                     "N/A: MAXVPN_LAN_CLIENT_IP is not a usable IPv4 client address; auxiliary check skipped")
            else:
                addr_rc, addr_out, addr_err = run(["ip", "-4", "-o", "addr", "show", "dev", "br-lan"])
                lan_networks = []
                router_addresses = set()
                for token in re.findall(r"\binet\s+(\d{1,3}(?:\.\d{1,3}){3}/\d+)\b", addr_out):
                    try:
                        iface = ipaddress.ip_interface(token)
                    except ValueError:
                        continue
                    if iface.version == 4:
                        lan_networks.append(iface.network)
                        router_addresses.add(str(iface.ip))
                source_on_lan = any(lan_source in network for network in lan_networks)
                if not source_on_lan or str(lan_source) in router_addresses:
                    detail = f"N/A: {LAN_CLIENT_IP} is not a client host on br-lan; source-aware lookup skipped"
                    if addr_rc and addr_err.strip():
                        detail += f" ({addr_err.strip()})"
                    note("INFO", f"source-aware unmarked LAN lookup for {address}", detail)
                else:
                    lan_rc, lan_out, lan_err = run([
                        "ip", "-4", "route", "get", address,
                        "from", str(lan_source), "iif", "br-lan",
                    ])
                    if lan_rc == 0 and lan_out.strip():
                        note("INFO", f"source-aware unmarked LAN lookup for {address} from {lan_source}", " ".join(lan_out.split()))
                    else:
                        note("INFO", f"source-aware unmarked LAN lookup for {address} unavailable",
                             f"auxiliary check only; {lan_err.strip() or f'exit code {lan_rc}'}")

print("\n== Summary ==", flush=True)
if failures:
    print(f"FAIL: {failures} required check(s) failed; WARN: {warnings}. No runtime configuration was changed.", flush=True)
    sys.exit(1)
if warnings:
    print(f"PASS: required IPv4 configuration checks passed; WARN: {warnings}. Review warnings above. No runtime configuration was changed.", flush=True)
else:
    print("PASS: all required IPv4 checks passed. No runtime configuration was changed.", flush=True)
PY
  exit $?
fi

# capture mode: resolve and validate the destination first; the actual capture
# runs as a direct SSH command with a PTY so Ctrl+C reaches tcpdump remotely.
DOMAIN="${DOMAINS[0]}"
echo "Connecting to ${ROUTER} to validate ${DOMAIN}..."
PREFLIGHT="$(ssh "$ROUTER" python3 - "$DOMAIN" <<'PY'
import ipaddress
import re
import subprocess
import sys

domain = sys.argv[1]
def run(args):
    return subprocess.run(args, text=True, capture_output=True, timeout=10)

try:
    r = run(["nslookup", domain, "127.0.0.1"])
except Exception as exc:
    print(f"ERROR={exc}")
    sys.exit(1)
lines = r.stdout.splitlines()
values = []
indexes = [i for i, line in enumerate(lines) if re.match(r"^\s*Name\s*:", line, re.I)]
selected = lines[indexes[0] + 1:] if indexes else lines
for line in selected:
    if indexes or (re.search(r"\bAddress\s*\d*\s*:", line, re.I) and re.search(re.escape(domain), line, re.I)):
        values.extend(re.findall(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])", line))
addresses = []
for value in values:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        continue
    if address.version == 4 and not address.is_loopback and not address.is_unspecified and not address.is_multicast:
        normalized = str(address)
        if normalized not in addresses:
            addresses.append(normalized)
if r.returncode or not addresses:
    print("ERROR=No IPv4 A record returned by router resolver")
    print(r.stderr.strip() or r.stdout.strip())
    sys.exit(1)
ip = addresses[0]
print(f"DOMAIN={domain}")
print(f"IP={ip}")
set_result = run(["ipset", "test", "MAXVPN_DIRECT", ip])
print(f"DIRECT_SET={'PASS' if set_result.returncode == 0 else 'FAIL'}")
route = run(["ip", "-4", "route", "get", ip, "mark", "0x64"])
route_text = " ".join(route.stdout.split())
route_ok = route.returncode == 0 and re.search(r"\btable\s+200\b", route_text) and re.search(r"\bdev\s+eth1\b", route_text) and re.search(r"\bmark\s+0x64\b", route_text.lower())
print(f"MARKED_ROUTE={'PASS' if route_ok else 'FAIL'}")
print(f"ROUTE={route_text or route.stderr.strip()}")
if set_result.returncode or not route_ok:
    print("ERROR=Capture not started: domain IP is not ready for a confirmed DIRECT/WAN observation")
    sys.exit(2)
# Snapshot the shared DIRECT counter during this same SSH call.
c = run(["iptables", "-t", "mangle", "-L", "PREROUTING", "-nvx", "--line-numbers"])
if c.returncode == 0:
    for line in c.stdout.splitlines():
        low = line.lower()
        if "match-set maxvpn_direct dst" in low and "0x64/0xff" in low and "mark" in low:
            m = re.match(r"^\s*\d+\s+(\d+)\s+(\d+)\s+", line)
            if m:
                print(f"COUNTER_BEFORE={m.group(1)} {m.group(2)}")
                break
PY
)" || {
  printf '%s\n' "$PREFLIGHT"
  echo 'Preflight failed; capture was not started.' >&2
  exit 1
}
printf '\n%s\n' "$PREFLIGHT"
TARGET_IP="$(printf '%s\n' "$PREFLIGHT" | sed -n 's/^IP=//p' | head -n 1)"
if [[ ! "$TARGET_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  echo 'Could not parse router-resolved IPv4 address; capture was not started.' >&2
  exit 1
fi

# Read the baseline counter returned by the preflight SSH call.
COUNTER_BEFORE="$(printf '%s\n' "$PREFLIGHT" | sed -n 's/^COUNTER_BEFORE=//p' | head -n 1)"
if [[ ! "$COUNTER_BEFORE" =~ ^[0-9]+[[:space:]][0-9]+$ ]]; then
  COUNTER_BEFORE="UNAVAILABLE"
fi

cat <<EOF

MaxVPN Smart Routing — interactive IPv4 packet capture
Domain: ${DOMAIN}
Target: ${TARGET_IP}:443 on WAN interface eth1
IPv6: N/A — провайдер не предоставляет IPv6; ничего не изменяется.

1. Open a separate Windows PowerShell on a device connected to this LAN.
2. Run the command below while this capture is running:
   curl.exe -I --resolve "${DOMAIN}:443:${TARGET_IP}" --connect-timeout 8 --max-time 12 "https://${DOMAIN}/"
3. Return to this terminal and press Ctrl+C after the request finishes.

The capture is live and has no timer. tcpdump will not write a capture file.
Press Enter to start capture, or Ctrl+C to cancel.
EOF
read -r _

set +e
ssh -tt "$ROUTER" "tcpdump -ni eth1 -nn -tttt 'host ${TARGET_IP} and tcp port 443'"
CAPTURE_RC=$?
set -e

COUNTER_AFTER="$(ssh "$ROUTER" python3 - <<'PY'
import re, subprocess
p = subprocess.run(["iptables", "-t", "mangle", "-L", "PREROUTING", "-nvx", "--line-numbers"], text=True, capture_output=True)
if p.returncode:
    print("UNAVAILABLE")
    raise SystemExit(0)
for line in p.stdout.splitlines():
    low = line.lower()
    if "match-set maxvpn_direct dst" in low and "0x64/0xff" in low and "mark" in low:
        m = re.match(r"^\s*\d+\s+(\d+)\s+(\d+)\s+", line)
        if m:
            print(f"{m.group(1)} {m.group(2)}")
            raise SystemExit(0)
print("UNAVAILABLE")
PY
)" || COUNTER_AFTER="UNAVAILABLE"

printf '\n== Capture summary ==\n'
printf 'tcpdump/SSH exit code: %s (Ctrl+C is expected when ending capture)\n' "$CAPTURE_RC"
if [[ "$COUNTER_BEFORE" =~ ^[0-9]+[[:space:]][0-9]+$ && "$COUNTER_AFTER" =~ ^[0-9]+[[:space:]][0-9]+$ ]]; then
  read -r before_packets before_bytes <<<"$COUNTER_BEFORE"
  read -r after_packets after_bytes <<<"$COUNTER_AFTER"
  printf 'MAXVPN_DIRECT shared PREROUTING counter delta: %+d packets, %+d bytes\n' "$((after_packets-before_packets))" "$((after_bytes-before_bytes))"
  echo 'Note: the counter is shared by all matching LAN traffic, not domain-specific.'
else
  echo 'WARN: unable to read one or both shared mangle counters.'
fi
printf 'Capture completed. Review the tcpdump output above for outbound packets and replies.\n'
echo 'No runtime configuration was changed; IPv6 remains out of scope.'
