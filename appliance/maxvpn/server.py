#!/usr/bin/env python3
import argparse
import csv
from contextlib import contextmanager
import fcntl
import io
import hashlib
import ipaddress
import json
import logging
import os
import re
import shlex
import sqlite3
import subprocess
import time
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_network
from pathlib import Path
from urllib.parse import urlparse

from vless_control import VlessControl, VlessControlError

VLESS_CONTROL = VlessControl()
LOG = logging.getLogger("maxvpn-appliance")

HOST = "127.0.0.1"
PORT = 8787
ROOT = Path(os.environ.get("MAXVPN_APPLIANCE_ROOT", "/opt/maxvpn-appliance"))
DATA = ROOT / "data"
DB = DATA / "maxvpn.db"
LOCK = ROOT / "run" / "apply.lock"
WEB = Path("/www/maxvpn")
WAN_IF = "eth1"
WAN_GW = ""
LAN_IF = "br-lan"
VPN_IF = "WireGuard"
RUNTIME_MODE_FILE = Path("/etc/maxvpn/runtime-mode")
FIREWALL_USER_SCRIPT = Path("/etc/maxvpn/firewall.user")
DIRECT_IPSET = "MAXVPN_DIRECT"
STATIC_IPSET = "MAXVPN_DIRECT_STATIC"
STATIC_NET_IPSET = "MAXVPN_DIRECT_STATIC_NET"
TABLE = "200"
FWMARK = "0x64/0xff"
START_TIME = time.time()
APPLIED_HASH_FILE = DATA / "applied_rules.sha256"
SELECTION_MONITOR_INTERVAL_SECONDS = 15
VLESS_WAN_FALLBACK_INTERVAL_SECONDS = 15
SELECTION_MONITOR_LOCK = threading.RLock()
SELECTION_MONITOR_STATE = {
    "enabled": True,
    "interval_seconds": SELECTION_MONITOR_INTERVAL_SECONDS,
    "last_attempt_at": None,
    "last_success_at": None,
    "last_error": None,
}
SELECTION_CURRENT_SNAPSHOT = None

ROOT.mkdir(parents=True, exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)
(ROOT / "run").mkdir(parents=True, exist_ok=True)


def run(cmd, check=True):
    p = subprocess.run(cmd, text=True, capture_output=True)
    if check and p.returncode != 0:
        raise RuntimeError(
            f"command failed rc={p.returncode}: {cmd!r}: {p.stderr.strip()}"
        )
    return p


def shell(cmd, check=True):
    p = subprocess.run(["sh", "-c", cmd], text=True, capture_output=True)
    if check and p.returncode != 0:
        raise RuntimeError(
            f"shell failed rc={p.returncode}: {cmd!r}: {p.stderr.strip()}"
        )
    return p


def uci_get(path, default=""):
    p = run(["uci", "-q", "get", path], check=False)
    return p.stdout.strip() if p.returncode == 0 else default


def discover_network():
    global WAN_IF, WAN_GW
    # Never retain a gateway from an earlier discovery when WAN loses its default route.
    WAN_GW = ""
    WAN_IF = uci_get("network.wan.device", "eth1") or "eth1"
    route = run(["ip", "route", "show", "default"], check=False).stdout
    m = re.search(r"default via (\S+) dev (\S+)", route)
    if m:
        WAN_GW = m.group(1)
        WAN_IF = m.group(2)
    return WAN_IF, WAN_GW


def db():
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    c.execute("""
        CREATE TABLE IF NOT EXISTS rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_type TEXT NOT NULL CHECK(target_type IN ('domain','cidr')),
            target TEXT NOT NULL UNIQUE,
            action TEXT NOT NULL DEFAULT 'direct' CHECK(action='direct'),
            priority INTEGER NOT NULL DEFAULT 100,
            address_family TEXT NOT NULL DEFAULT 'any',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL,
            comment TEXT NOT NULL DEFAULT ''
        )
    """)
    columns = {row[1] for row in c.execute("PRAGMA table_info(rules)").fetchall()}
    if "comment" not in columns:
        c.execute("ALTER TABLE rules ADD COLUMN comment TEXT NOT NULL DEFAULT ''")
    c.commit()
    return c


def find_ipset_section(name):
    text = run(["uci", "show", "dhcp"], check=False).stdout
    for line in text.splitlines():
        if line.endswith(".name='" + name + "'"):
            return line.split(".name=", 1)[0]
    return None


def read_domains_from_uci():
    section = find_ipset_section(DIRECT_IPSET)
    if not section:
        return []
    out = uci_get(section + ".domain", "")
    if not out:
        return []
    try:
        return shlex.split(out)
    except Exception:
        return re.findall(r"'([^']+)'", out)


def seed_rules():
    c = db()
    count = c.execute("SELECT COUNT(*) FROM rules").fetchone()[0]
    if count:
        c.close()
        return
    now = int(time.time())
    domains = read_domains_from_uci()
    for i, target in enumerate(domains, 1):
        if target and "." in target:
            c.execute(
                "INSERT OR IGNORE INTO rules(target_type,target,action,priority,address_family,enabled,created_at) VALUES(?,?,?,?,?,?,?)",
                ("domain", target.strip().lower(), "direct", i * 10, "any", 1, now),
            )
    static = run(["ipset", "save", STATIC_IPSET], check=False).stdout
    for line in static.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "add" and parts[1] == STATIC_IPSET:
            target = parts[2]
            c.execute(
                "INSERT OR IGNORE INTO rules(target_type,target,action,priority,address_family,enabled,created_at) VALUES(?,?,?,?,?,?,?)",
                ("cidr", target, "direct", 1000, "ipv4", 1, now),
            )
    c.commit()
    c.close()


def _selection_timestamp():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _selection_latest_delay(proxy_info):
    if not isinstance(proxy_info, dict):
        return {"delay_ms": None, "observed_at": None}
    history = proxy_info.get("history")
    if not isinstance(history, list) or not history:
        return {"delay_ms": None, "observed_at": None}
    entries = [item for item in history if isinstance(item, dict)]
    if not entries:
        return {"delay_ms": None, "observed_at": None}
    latest = max(entries, key=lambda item: str(item.get("time") or ""))
    delay = latest.get("delay")
    if isinstance(delay, bool) or not isinstance(delay, int) or delay <= 0:
        delay = None
    observed_at = latest.get("time")
    if not isinstance(observed_at, str):
        observed_at = None
    return {"delay_ms": delay, "observed_at": observed_at}


def _selection_urltest_settings():
    try:
        config_path = getattr(
            VLESS_CONTROL, "config_file", Path("/etc/maxvpn/sing-box-vless.json")
        )
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        outbounds = config.get("outbounds", [])
        if not isinstance(outbounds, list):
            return None, None
        group = next(
            (
                item
                for item in outbounds
                if isinstance(item, dict)
                and item.get("tag") == "vless-auto"
                and item.get("type") == "urltest"
            ),
            None,
        )
        if not isinstance(group, dict):
            return None, None
        interval = group.get("interval")
        tolerance = group.get("tolerance")
        if not isinstance(interval, str):
            interval = None
        if isinstance(tolerance, bool) or not isinstance(tolerance, int):
            tolerance = None
        return interval, tolerance
    except (OSError, ValueError, TypeError):
        return None, None


def _selection_snapshot_from_payload(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("proxies"), dict):
        raise RuntimeError("sing-box Clash API returned an invalid proxies payload")
    proxies = payload["proxies"]
    selector = proxies.get("vless-out")
    if not isinstance(selector, dict):
        raise RuntimeError("sing-box Clash API did not report vless-out")
    selected = selector.get("now")
    if selected == "vless-auto":
        selection_mode = "auto"
        auto_group = proxies.get("vless-auto")
        active = auto_group.get("now") if isinstance(auto_group, dict) else None
    elif isinstance(selected, str) and re.fullmatch(
        r"vless-profile-[1-9][0-9]*", selected
    ):
        selection_mode = "manual"
        active = selected
    else:
        raise RuntimeError("sing-box selector did not report a recognized outbound")
    if active is not None and not re.fullmatch(
        r"vless-profile-[1-9][0-9]*", str(active)
    ):
        active = None

    profile_delays = {}
    for tag, proxy_info in proxies.items():
        if not isinstance(tag, str) or not re.fullmatch(
            r"vless-profile-[1-9][0-9]*", tag
        ):
            continue
        profile_delays[tag] = _selection_latest_delay(proxy_info)

    interval, tolerance = _selection_urltest_settings()
    active_sample = profile_delays.get(active, {}) if active else {}
    return {
        "observed_at": _selection_timestamp(),
        "observed_at_epoch": time.time(),
        "selection_mode": selection_mode,
        "selected_outbound": selected,
        "active_outbound": active,
        "active_delay_ms": active_sample.get("delay_ms"),
        "active_delay_observed_at": active_sample.get("observed_at"),
        "profile_delays": profile_delays,
        "urltest_interval": interval,
        "urltest_tolerance_ms": tolerance,
    }


def _read_vless_selection_snapshot():
    result = run(
        ["curl", "-fsS", "--max-time", "3", "http://127.0.0.1:9090/proxies"],
        check=False,
    )
    if getattr(result, "returncode", 1) != 0:
        raise RuntimeError("sing-box Clash API is unavailable")
    try:
        payload = json.loads(getattr(result, "stdout", "") or "{}")
    except (ValueError, TypeError) as exc:
        raise RuntimeError("sing-box Clash API returned invalid JSON") from exc
    return _selection_snapshot_from_payload(payload)


def _vless_selection_monitor_loop():
    global SELECTION_CURRENT_SNAPSHOT
    while True:
        attempted_at = _selection_timestamp()
        with SELECTION_MONITOR_LOCK:
            SELECTION_MONITOR_STATE["last_attempt_at"] = attempted_at
        try:
            snapshot = _read_vless_selection_snapshot()
            VLESS_CONTROL.record_selection_observation(snapshot)
        except Exception as exc:
            with SELECTION_MONITOR_LOCK:
                # The monitor records only a bounded error string, never config contents.
                SELECTION_MONITOR_STATE["last_error"] = str(exc).replace("\n", " ")[
                    :180
                ]
        else:
            with SELECTION_MONITOR_LOCK:
                SELECTION_CURRENT_SNAPSHOT = snapshot
                SELECTION_MONITOR_STATE["last_success_at"] = snapshot["observed_at"]
                SELECTION_MONITOR_STATE["last_error"] = None
        time.sleep(SELECTION_MONITOR_INTERVAL_SECONDS)


def _vless_wan_fallback_loop():
    while True:
        try:
            result = VLESS_CONTROL.monitor_wan_fallback()
            if result.get("action") in {"fallback-to-wan", "recovered-to-vless"}:
                LOG.info("VLESS WAN fallback transition: %s", result["action"])
            if result.get("action") in {
                "fallback-failed",
                "recovery-failed",
                "recovery-probe-start-failed",
                "restore-failed",
                "probe-failed",
            }:
                LOG.warning("VLESS WAN fallback monitor: %s", result)
        except Exception:
            LOG.exception("VLESS WAN fallback monitor failed")
        time.sleep(VLESS_WAN_FALLBACK_INTERVAL_SECONDS)


def _vless_selection_history_payload():
    with SELECTION_MONITOR_LOCK:
        monitor = dict(SELECTION_MONITOR_STATE)
        current = (
            dict(SELECTION_CURRENT_SNAPSHOT)
            if isinstance(SELECTION_CURRENT_SNAPSHOT, dict)
            else None
        )
    return VLESS_CONTROL.get_selection_history(monitor=monitor, current=current)


def status_runtime():
    discover_network()
    return {
        "project": "MaxVPN",
        "appliance": "brume3",
        "status": "running",
        "uptime_seconds": int(time.time() - START_TIME),
        "python": os.sys.version.split()[0],
        "board": board_info(),
        "vpn": vpn_info(),
        "smart_routing": routing_info(),
    }


def board_info():
    ub = run(["ubus", "call", "system", "board"], check=False)
    try:
        return json.loads(ub.stdout)
    except Exception:
        return {"raw": ub.stdout.strip()}


def vpn_info():
    p = run(["awg", "show", VPN_IF], check=False)
    if p.returncode != 0:
        return {"interface": VPN_IF, "connected": False, "runtime": p.stderr.strip()}
    raw = p.stdout
    handshake = rx = tx = endpoint = port = keepalive = None
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("listening port:"):
            port = s.split(":", 1)[1].strip()
        elif s.startswith("endpoint:"):
            endpoint = s.split(":", 1)[1].strip() if ":" in s else s.split(None, 1)[1]
        elif s.startswith("latest handshake:"):
            handshake = s.split(":", 1)[1].strip()
        elif s.startswith("transfer:"):
            parts = s.split()
            if len(parts) >= 6:
                rx = " ".join(parts[1:3])
                tx = " ".join(parts[4:6])
        elif s.startswith("persistent keepalive:"):
            keepalive = s.split(":", 1)[1].strip()
    return {
        "interface": VPN_IF,
        "connected": bool(raw.strip()),
        "listening_port": port,
        "endpoint": endpoint,
        "latest_handshake": handshake,
        "transfer": {"received": rx, "sent": tx},
        "persistent_keepalive": keepalive,
        "runtime": raw,
    }


def ipset_type(name):
    text = run(["ipset", "list", name], check=False).stdout
    for line in text.splitlines():
        if line.startswith("Type:"):
            return line.split(":", 1)[1].strip()
    return None


def matching_mangle_rules(ipset_name):
    text = run(["iptables", "-t", "mangle", "-S", "PREROUTING"], check=False).stdout
    return [
        line.strip()
        for line in text.splitlines()
        if f"--match-set {ipset_name} dst" in line
    ]


def routing_info():
    rules = run(["ip", "rule", "show"], check=False).stdout.strip()
    table = run(["ip", "route", "show", "table", TABLE], check=False).stdout.strip()
    direct = run(["ipset", "list", DIRECT_IPSET], check=False).stdout
    static = run(["ipset", "list", STATIC_IPSET], check=False).stdout
    static_net = run(["ipset", "list", STATIC_NET_IPSET], check=False).stdout
    current_hash = rule_config_hash()
    applied_hash = get_applied_hash()
    return {
        "ip_rule": rules,
        "table_200": table,
        "config_hash": current_hash,
        "applied_config_hash": applied_hash,
        "config_dirty": bool(applied_hash and current_hash != applied_hash),
        "direct_ipset": DIRECT_IPSET in direct,
        "static_ipset": STATIC_IPSET in static,
        "static_ipset_type": ipset_type(STATIC_IPSET),
        "static_net_ipset": STATIC_NET_IPSET in static_net,
        "mangle_direct": bool(matching_mangle_rules(DIRECT_IPSET)),
        "mangle_static": bool(matching_mangle_rules(STATIC_IPSET)),
        "mangle_static_net": bool(matching_mangle_rules(STATIC_NET_IPSET)),
        "mangle_direct_count": len(matching_mangle_rules(DIRECT_IPSET)),
        "mangle_static_count": len(matching_mangle_rules(STATIC_IPSET)),
        "mangle_static_net_count": len(matching_mangle_rules(STATIC_NET_IPSET)),
        "wan_interface": WAN_IF,
        "wan_gateway": WAN_GW,
    }


def list_rules():
    c = db()
    rows = c.execute("SELECT * FROM rules ORDER BY priority,id").fetchall()
    c.close()
    return [dict(r) | {"enabled": bool(r["enabled"])} for r in rows]


def rule_config_hash(rows=None):
    if rows is None:
        rows = list_rules()
    normalized = []
    for r in rows:
        normalized.append(
            {
                "target_type": r["target_type"],
                "target": r["target"],
                "action": r["action"],
                "priority": int(r["priority"]),
                "address_family": r["address_family"],
                "enabled": bool(r["enabled"]),
            }
        )
    normalized.sort(key=lambda x: (x["priority"], x["target_type"], x["target"]))
    payload = json.dumps(
        normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_applied_hash():
    try:
        value = APPLIED_HASH_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return value if re.fullmatch(r"[0-9a-f]{64}", value) else ""


def set_applied_hash(value):
    tmp = APPLIED_HASH_FILE.with_suffix(".tmp")
    tmp.write_text(value + "\n", encoding="utf-8")
    os.replace(tmp, APPLIED_HASH_FILE)


_ROUTING_LOCK_STATE = threading.local()


@contextmanager
def routing_lock():
    """Serialize Smart Routing changes across processes and nested calls."""
    depth = getattr(_ROUTING_LOCK_STATE, "depth", 0)
    if depth:
        _ROUTING_LOCK_STATE.depth = depth + 1
        try:
            yield
        finally:
            _ROUTING_LOCK_STATE.depth -= 1
        return

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock_file = LOCK.open("a", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        _ROUTING_LOCK_STATE.depth = 1
        try:
            yield
        finally:
            del _ROUTING_LOCK_STATE.depth
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    finally:
        lock_file.close()


def ensure_applied_baseline(force=False):
    """Restore Smart Routing only when its persisted configuration is dirty.

    applied_rules.sha256 is a record of a successful apply_routing() call.
    Treat a missing or invalid value as dirty rather than accepting the current
    SQLite configuration as a new baseline: otherwise a reboot after lost
    runtime state could make the service report a clean configuration without
    recreating its DNS, ipset, mangle, and policy-routing state.

    A failed restore deliberately leaves the last applied hash unchanged. The
    API still starts, so the error can be inspected and an operator can retry
    the existing explicit Apply action; this startup path never controls VLESS
    or AmneziaWG.

    Returns True only when this invocation successfully applied routing.
    """
    with routing_lock():
        current_hash = rule_config_hash()
        applied_hash = get_applied_hash()
        if current_hash == applied_hash and not force:
            LOG.info(
                "Smart Routing startup restore skipped: config hash %s is already applied",
                current_hash,
            )
            return False

        if force:
            LOG.warning(
                "Smart Routing runtime restore forced for config hash %s",
                current_hash,
            )
        else:
            LOG.warning(
                "Smart Routing startup restore required: config hash %s differs from applied hash %s",
                current_hash,
                applied_hash or "<missing>",
            )
        try:
            apply_routing()
        except Exception:
            LOG.exception(
                "Smart Routing startup restore failed; preserving the previous applied hash"
            )
            return False

        restored_hash = get_applied_hash()
        if restored_hash != current_hash:
            LOG.error(
                "Smart Routing startup restore finished without confirming the expected applied hash "
                "(expected=%s, actual=%s)",
                current_hash,
                restored_hash or "<missing>",
            )
            return False

        LOG.info(
            "Smart Routing startup restore completed for config hash %s", current_hash
        )
        return True


def _read_firewall_chain_rules(command, chain):
    result = run(command, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"firewall inspection failed for {chain}: {(result.stderr or '').strip()}"
        )

    prefix = f"-A {chain} "
    return [
        line.strip()
        for line in (result.stdout or "").splitlines()
        if line.strip().startswith(prefix)
    ]


def _require_exact_firewall_rules(actual, expected, description):
    if actual != expected:
        raise RuntimeError(
            f"{description} mismatch: expected={expected!r}, actual={actual!r}"
        )


def verify_runtime_firewall():
    """Verify the complete firewall policy selected by runtime-mode."""
    try:
        mode = RUNTIME_MODE_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        mode = "vpn"

    if mode not in ("vpn", "vless", "wan"):
        mode = "vpn"

    if mode == "wan":
        ipv4_expected = [
            "-A MAXVPN_LAN_FORWARD -i br-lan -o eth1 -j ACCEPT",
            "-A MAXVPN_LAN_FORWARD -j RETURN",
        ]
        ipv6_expected = [
            "-A MAXVPN_LAN6_FORWARD -i br-lan -o eth1 -j ACCEPT",
            "-A MAXVPN_LAN6_FORWARD -j RETURN",
        ]
    elif mode == "vless":
        ipv4_expected = [
            "-A MAXVPN_LAN_FORWARD -i br-lan -o maxvpn0 -j ACCEPT",
            "-A MAXVPN_LAN_FORWARD -i br-lan -o eth1 -m mark --mark 0x64/0xff -j ACCEPT",
            "-A MAXVPN_LAN_FORWARD -i br-lan -o eth1 -j DROP",
            "-A MAXVPN_LAN_FORWARD -j RETURN",
        ]
        ipv6_expected = [
            "-A MAXVPN_LAN6_FORWARD -i br-lan -j DROP",
            "-A MAXVPN_LAN6_FORWARD -j RETURN",
        ]
    else:
        ipv4_expected = [
            "-A MAXVPN_LAN_FORWARD -i br-lan -o WireGuard -j ACCEPT",
            "-A MAXVPN_LAN_FORWARD -i br-lan -o eth1 -m mark --mark 0x64/0xff -j ACCEPT",
            "-A MAXVPN_LAN_FORWARD -i br-lan -o eth1 -j DROP",
            "-A MAXVPN_LAN_FORWARD -j RETURN",
        ]
        ipv6_expected = [
            "-A MAXVPN_LAN6_FORWARD -i br-lan -o WireGuard -j ACCEPT",
            "-A MAXVPN_LAN6_FORWARD -i br-lan -o eth1 -j DROP",
            "-A MAXVPN_LAN6_FORWARD -j RETURN",
        ]

    ipv4_rules = _read_firewall_chain_rules(
        ["iptables", "-S", "MAXVPN_LAN_FORWARD"],
        "MAXVPN_LAN_FORWARD",
    )
    ipv4_forwarding = _read_firewall_chain_rules(
        ["iptables", "-S", "forwarding_rule"],
        "forwarding_rule",
    )
    ipv6_rules = _read_firewall_chain_rules(
        ["ip6tables", "-S", "MAXVPN_LAN6_FORWARD"],
        "MAXVPN_LAN6_FORWARD",
    )
    ipv6_forwarding = _read_firewall_chain_rules(
        ["ip6tables", "-S", "forwarding_rule"],
        "forwarding_rule",
    )
    nat_rules = _read_firewall_chain_rules(
        ["iptables", "-t", "nat", "-S", "MAXVPN_DIRECT_NAT"],
        "MAXVPN_DIRECT_NAT",
    )
    postrouting_rules = _read_firewall_chain_rules(
        ["iptables", "-t", "nat", "-S", "POSTROUTING"],
        "POSTROUTING",
    )

    _require_exact_firewall_rules(ipv4_rules, ipv4_expected, "IPv4 forwarding chain")
    _require_exact_firewall_rules(ipv6_rules, ipv6_expected, "IPv6 forwarding chain")

    expected_ipv4_jump = "-A forwarding_rule -j MAXVPN_LAN_FORWARD"
    expected_ipv6_jump = "-A forwarding_rule -j MAXVPN_LAN6_FORWARD"
    expected_nat_jump = "-A POSTROUTING -j MAXVPN_DIRECT_NAT"

    if (
        ipv4_forwarding.count(expected_ipv4_jump) != 1
        or not ipv4_forwarding
        or ipv4_forwarding[0] != expected_ipv4_jump
    ):
        raise RuntimeError(
            "IPv4 firewall chain must be attached exactly once "
            "and first in forwarding_rule"
        )

    if (
        ipv6_forwarding.count(expected_ipv6_jump) != 1
        or not ipv6_forwarding
        or ipv6_forwarding[0] != expected_ipv6_jump
    ):
        raise RuntimeError(
            "IPv6 firewall chain must be attached exactly once "
            "and first in forwarding_rule"
        )

    nat_expected = [
        "-A MAXVPN_DIRECT_NAT -o eth1 -m mark --mark 0x64/0xff -j MASQUERADE",
        "-A MAXVPN_DIRECT_NAT -j RETURN",
    ]
    _require_exact_firewall_rules(nat_rules, nat_expected, "DIRECT NAT chain")

    if (
        postrouting_rules.count(expected_nat_jump) != 1
        or not postrouting_rules
        or postrouting_rules[0] != expected_nat_jump
    ):
        raise RuntimeError(
            "DIRECT NAT chain must be attached exactly once and first in POSTROUTING"
        )

    return {
        "mode": mode,
        "ipv4": True,
        "ipv6": True,
        "nat": True,
        "nat_jump_count": 1,
    }


def restore_runtime_firewall():
    """Run the installed firewall policy and verify its actual runtime state."""
    if not FIREWALL_USER_SCRIPT.is_file():
        raise RuntimeError(f"MaxVPN firewall script is missing: {FIREWALL_USER_SCRIPT}")

    if not os.access(str(FIREWALL_USER_SCRIPT), os.X_OK):
        raise RuntimeError(
            f"MaxVPN firewall script is not executable: {FIREWALL_USER_SCRIPT}"
        )

    # -e makes command failures inside firewall.user visible to the caller.
    result = run(
        ["/bin/sh", "-e", str(FIREWALL_USER_SCRIPT)],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "MaxVPN firewall script failed: "
            f"rc={result.returncode}, stderr={(result.stderr or '').strip()}"
        )

    return verify_runtime_firewall()


def restore_routing_exit_code():
    """Force Smart Routing and firewall restoration; return a shell status."""
    with routing_lock():
        if not ensure_applied_baseline(force=True):
            LOG.error("Smart Routing forced runtime restore failed")
            return 1

        try:
            firewall_state = restore_runtime_firewall()
        except Exception:
            LOG.exception("MaxVPN runtime firewall restoration failed")
            return 1

        LOG.info(
            "Smart Routing and firewall restore completed: mode=%s, NAT jumps=%s",
            firewall_state["mode"],
            firewall_state["nat_jump_count"],
        )
        return 0


def validate_target(target_type, target):
    target = target.strip().lower()
    if not target:
        raise ValueError("target is required")
    if target_type == "domain":
        if len(target) > 253 or " " in target or "/" in target:
            raise ValueError("invalid domain")
        target = target.strip(".")
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", target):
            raise ValueError("invalid domain")
        return target
    if target_type == "cidr":
        try:
            net = ip_network(target, strict=False)
        except ValueError as e:
            raise ValueError(f"invalid CIDR: {e}")
        if net.version != 4:
            raise ValueError("only IPv4 CIDR is supported in appliance phase 3")
        return str(net)
    raise ValueError("target_type must be domain or cidr")


def validate_comment(comment):
    if comment is None:
        return ""
    comment = str(comment).strip()
    if len(comment) > 500:
        raise ValueError("comment must be 500 characters or fewer")
    return comment


def update_dnsmasq_domains(domains):
    section = find_ipset_section(DIRECT_IPSET)
    if not section:
        raise RuntimeError(f"{DIRECT_IPSET} ipset not found in /etc/config/dhcp")
    # UCI removes the option entirely when the last domain is deleted. A
    # subsequent apply/boot restore must still work for CIDR-only/empty rules.
    option = section + ".domain"
    if run(["uci", "-q", "get", option], check=False).returncode == 0:
        run(["uci", "-q", "delete", option])
    for d in domains:
        shell(f"uci add_list {shlex.quote(section)}.domain={shlex.quote(d)}")
    shell("uci commit dhcp")
    shell("/etc/init.d/dnsmasq reload")


def ensure_ipset(name, ipset_type_name):
    existing = ipset_type(name)
    if existing is None:
        run(["ipset", "create", name, ipset_type_name, "family", "inet"])
        return ipset_type_name
    if existing != ipset_type_name:
        raise RuntimeError(
            f"ipset {name} has type {existing}, expected {ipset_type_name}"
        )
    return existing


def ensure_canonical_mark_rule(ipset_name):
    """Ensure exactly one canonical MaxVPN MARK rule for an ipset.

    Remove only recognized MaxVPN rules. Foreign rules sharing the same
    ipset are preserved.
    """
    listing = run(
        ["iptables", "-t", "mangle", "-S", "PREROUTING"],
        check=False,
    ).stdout

    managed_marks = {"0x64/0xff", "0x64/0xffffffff"}

    for line in listing.splitlines():
        line = line.strip()
        if not line.startswith("-A PREROUTING "):
            continue

        try:
            parts = shlex.split(line)
        except ValueError:
            continue

        # Match the exact rule shape emitted by iptables -S.
        expected = [
            "-A",
            "PREROUTING",
            "-i",
            LAN_IF,
            "-m",
            "set",
            "--match-set",
            ipset_name,
            "dst",
            "-j",
            "MARK",
            "--set-xmark",
        ]

        if len(parts) != len(expected) + 1:
            continue

        if parts[:-1] != expected:
            continue

        if parts[-1] not in managed_marks:
            continue

        delete_parts = parts.copy()
        delete_parts[0] = "-D"
        run(["iptables", "-t", "mangle", *delete_parts], check=False)

    canonical = [
        "iptables",
        "-t",
        "mangle",
        "-A",
        "PREROUTING",
        "-i",
        LAN_IF,
        "-m",
        "set",
        "--match-set",
        ipset_name,
        "dst",
        "-j",
        "MARK",
        "--set-xmark",
        FWMARK,
    ]
    run(canonical)


def remove_mangle_rule(ipset_name):
    legacy = [
        "iptables",
        "-t",
        "mangle",
        "-D",
        "PREROUTING",
        "-i",
        LAN_IF,
        "-m",
        "set",
        "--match-set",
        ipset_name,
        "dst",
        "-j",
        "MARK",
        "--set-xmark",
        "0x64/0xffffffff",
    ]
    canonical = [
        "iptables",
        "-t",
        "mangle",
        "-D",
        "PREROUTING",
        "-i",
        LAN_IF,
        "-m",
        "set",
        "--match-set",
        ipset_name,
        "dst",
        "-j",
        "MARK",
        "--set-xmark",
        FWMARK,
    ]
    while run([*legacy], check=False).returncode == 0:
        pass
    while run([*canonical], check=False).returncode == 0:
        pass


def rebuild_static_ipsets(cidrs):
    ensure_ipset(STATIC_IPSET, "hash:ip")
    run(["ipset", "flush", STATIC_IPSET])

    broad_networks = []
    for target in cidrs:
        net = ip_network(target, strict=False)
        if net.version != 4:
            raise RuntimeError(f"only IPv4 CIDR is supported: {target}")
        if net.prefixlen == 32:
            run(["ipset", "add", STATIC_IPSET, str(net.network_address)])
        else:
            broad_networks.append(str(net))

    ensure_canonical_mark_rule(STATIC_IPSET)

    ensure_ipset(STATIC_NET_IPSET, "hash:net")
    run(["ipset", "flush", STATIC_NET_IPSET])
    for net in broad_networks:
        run(["ipset", "add", STATIC_NET_IPSET, net])
    if broad_networks:
        ensure_canonical_mark_rule(STATIC_NET_IPSET)
    else:
        remove_mangle_rule(STATIC_NET_IPSET)


def ensure_policy_rule():
    rule_lines = run(["ip", "-o", "rule", "show"], check=False).stdout.splitlines()
    expected = "100: from all fwmark 0x64/0xff lookup 200"
    priority_100 = [
        line.strip() for line in rule_lines if line.strip().startswith("100:")
    ]
    if priority_100:
        normalized = " ".join(priority_100[0].split())
        if normalized != expected:
            raise RuntimeError(
                "routing priority 100 is occupied by a different rule: "
                f"{priority_100[0]}"
            )
        # Detect duplicate copies of the same policy rule. The kernel normally
        # collapses them by priority, but we fail explicitly if multiple lines exist.
        if len(priority_100) > 1:
            raise RuntimeError("multiple routing rules exist at priority 100")
        return
    p = run(
        [
            "ip",
            "rule",
            "add",
            "priority",
            "100",
            "fwmark",
            "0x64/0xff",
            "lookup",
            "200",
        ],
        check=False,
    )
    if p.returncode != 0:
        stderr = (p.stderr or "").strip()
        if (
            "File exists" not in stderr
            and "RTNETLINK answers: File exists" not in stderr
        ):
            raise RuntimeError(f"ip rule add failed rc={p.returncode}: {stderr}")


def ensure_table_200_routes():
    if not WAN_GW:
        raise RuntimeError("WAN gateway not detected")
    lan_ip = uci_get("network.lan.ipaddr", "192.168.8.1")
    lan_network = str(ip_network(f"{lan_ip}/24", strict=False))
    run(
        [
            "ip",
            "route",
            "replace",
            "default",
            "via",
            WAN_GW,
            "dev",
            WAN_IF,
            "table",
            TABLE,
        ]
    )
    run(["ip", "route", "replace", lan_network, "dev", LAN_IF, "table", TABLE])
    # Keep the explicit gateway host route used by the current Brume runtime.
    run(
        [
            "ip",
            "route",
            "replace",
            f"{WAN_GW}/32",
            "via",
            WAN_GW,
            "dev",
            WAN_IF,
            "table",
            TABLE,
        ]
    )


def ensure_direct_path():
    ensure_ipset(DIRECT_IPSET, "hash:ip")
    ensure_canonical_mark_rule(DIRECT_IPSET)
    ensure_policy_rule()
    ensure_table_200_routes()


DNS_LOG = Path("/tmp/maxvpn-dns-events.log")
DIAGNOSTIC_MAX_READ = 256 * 1024
DIAGNOSTIC_DEFAULT_SECONDS = 30
DIAGNOSTICS = {}

_QUERY_RE = re.compile(
    r"dnsmasq\[(?P<pid>\d+)\]:\s+(?P<query_id>\d+)\s+"
    r"(?P<peer>\S+/\d+)\s+query\[(?P<qtype>[A-Z0-9]+)\]\s+"
    r"(?P<hostname>\S+)\s+from\s+(?P<source>\S+)"
)

_REPLY_RE = re.compile(
    r"dnsmasq\[(?P<pid>\d+)\]:\s+(?P<query_id>\d+)\s+"
    r"(?P<peer>\S+/\d+)\s+(?:reply|cached)\s+"
    r"(?P<hostname>\S+)\s+is\s+(?P<answer>\S+)"
)

_DIAGNOSTIC_DNS_NAME_RE = re.compile(
    r"(?i)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+\.?$"
)


_DIAGNOSTIC_SYSLOG_TIME_RE = re.compile(
    r"^(?P<month>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s+"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
)


def _diagnostic_time_of_day(line):
    """Return syslog time as seconds from midnight, or None if unavailable."""
    match = _DIAGNOSTIC_SYSLOG_TIME_RE.match(str(line or ""))
    if not match:
        return None
    return (
        int(match.group("hour")) * 3600
        + int(match.group("minute")) * 60
        + int(match.group("second"))
    )


def _normalize_diagnostic_domain(value):
    value = str(value or "").strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = value.split("/", 1)[0].split("?", 1)[0]
    value = value.strip(".")
    if not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
        r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+",
        value,
    ):
        raise ValueError("invalid diagnostic domain")
    return value


def _diagnostic_log_cursor():
    try:
        st = DNS_LOG.stat()
        return {"inode": int(st.st_ino), "offset": int(st.st_size)}
    except OSError:
        return {"inode": 0, "offset": 0}


def _diagnostic_read_delta(cursor):
    try:
        st = DNS_LOG.stat()
    except OSError:
        return "", dict(cursor), True

    inode = int(st.st_ino)
    size = int(st.st_size)
    reset = inode != int(cursor.get("inode", 0)) or size < int(cursor.get("offset", 0))
    offset = 0 if reset else int(cursor.get("offset", 0))

    if offset >= size:
        return "", {"inode": inode, "offset": size}, reset

    read_size = min(DIAGNOSTIC_MAX_READ, size - offset)

    with DNS_LOG.open("rb") as fh:
        fh.seek(offset)
        data = fh.read(read_size)

    return (
        data.decode("utf-8", errors="replace"),
        {"inode": inode, "offset": offset + len(data)},
        reset,
    )


def _diagnostic_direct_ips():
    result = run(["ipset", "list", DIRECT_IPSET], check=False)
    members = set()
    in_members = False
    for raw in (result.stdout or "").splitlines():
        line = raw.strip()
        if line == "Members:":
            in_members = True
            continue
        if in_members and re.fullmatch(r"\d+\.\d+\.\d+\.\d+", line):
            members.add(line)
    return members


def _diagnostic_domain_rules():
    c = db()
    rows = c.execute(
        "SELECT target FROM rules "
        "WHERE enabled=1 AND target_type='domain' "
        "ORDER BY priority,id"
    ).fetchall()
    c.close()
    return [str(row["target"]).strip().lower().rstrip(".") for row in rows]


def _diagnostic_rule_covers(hostname, rules):
    hostname = hostname.lower().rstrip(".")
    return any(hostname == rule or hostname.endswith("." + rule) for rule in rules)


def _diagnostic_parse(
    data,
    requested_client_ip,
    parser_state=None,
    reset=False,
):
    """Parse DNS deltas with transaction correlation, CNAME handling and query times."""
    if parser_state is None:
        parser_state = {}
    if reset:
        parser_state["transactions"] = {}

    transactions = parser_state.setdefault("transactions", {})
    selected_client_ip = str(
        requested_client_ip or parser_state.get("selected_client_ip") or ""
    ).strip()
    records = {}
    source_counts = {}

    def record_for(hostname, source, query_time=None):
        item = records.setdefault(
            hostname,
            {
                "hostname": hostname,
                "ips": set(),
                "queries": 0,
                "sources": set(),
                "query_times": set(),
            },
        )
        if source:
            item["sources"].add(source)
        if query_time is not None:
            item["query_times"].add(int(query_time))
        return item

    for raw in (data or "").splitlines():
        line = raw.strip()
        if not line:
            continue

        query = _QUERY_RE.search(line)
        if query:
            hostname = query.group("hostname").lower().rstrip(".")
            source = query.group("source").strip()
            qtype = query.group("qtype").upper()
            if not hostname or not source:
                continue

            query_time = _diagnostic_time_of_day(line)
            transaction_key = (
                query.group("pid"),
                query.group("query_id"),
                query.group("peer"),
            )
            transactions[transaction_key] = {
                "hostname": hostname,
                "source": source,
                "qtype": qtype,
                "query_time": query_time,
            }

            if not selected_client_ip or source == selected_client_ip:
                item = record_for(hostname, source, query_time)
                item["queries"] += 1
                source_counts[source] = source_counts.get(source, 0) + 1

            while len(transactions) > 4096:
                transactions.pop(next(iter(transactions)))
            continue

        reply = _REPLY_RE.search(line)
        if not reply:
            continue

        transaction_key = (
            reply.group("pid"),
            reply.group("query_id"),
            reply.group("peer"),
        )
        transaction = transactions.get(transaction_key)
        if transaction is None:
            continue

        source = transaction["source"]
        qtype = transaction["qtype"]
        original_hostname = transaction["hostname"]
        answer = str(reply.group("answer") or "").strip()
        try:
            parsed_ip = ipaddress.ip_address(answer)
        except ValueError:
            parsed_ip = None

        if qtype == "A" and isinstance(parsed_ip, ipaddress.IPv4Address):
            if not selected_client_ip or source == selected_client_ip:
                item = record_for(
                    original_hostname,
                    source,
                    transaction.get("query_time"),
                )
                item["ips"].add(str(parsed_ip))
            # Keep the transaction available for multi-address A replies.
            continue

        # Keep A-query transactions through cached CNAME hops. Some dnsmasq
        # versions log either the explicit <CNAME> token or an intermediate name.
        if qtype == "A" and (
            answer.lower() == "<cname>" or _DIAGNOSTIC_DNS_NAME_RE.fullmatch(answer)
        ):
            continue

        transactions.pop(transaction_key, None)

    if not selected_client_ip and source_counts:
        selected_client_ip = max(
            source_counts, key=lambda source: source_counts[source]
        )
    if selected_client_ip:
        parser_state["selected_client_ip"] = selected_client_ip

    result = []
    for item in records.values():
        if selected_client_ip and selected_client_ip not in item["sources"]:
            continue
        result.append(
            {
                "hostname": item["hostname"],
                "ips": sorted(item["ips"]),
                "queries": item["queries"],
                "query_times": sorted(item["query_times"]),
            }
        )
    return selected_client_ip, result


_DIAGNOSTIC_BRAND_ALIASES = {
    "2gis.ru": ("2gis.com",),
}


_DIAGNOSTIC_BACKGROUND_SUFFIXES = (
    "msftconnecttest.com",
    "msftncsi.com",
)
_DIAGNOSTIC_BACKGROUND_ZONES = (
    "in-addr.arpa",
    "ip6.arpa",
)


def _diagnostic_classify_resource(
    hostname,
    ips,
    direct_ips,
    rules,
    target_domain,
    query_times,
    target_times,
    relation_window_seconds=5,
):
    """Classify target, brand-alias, time-correlated and background DNS resources."""
    hostname = str(hostname or "").strip().lower().rstrip(".")
    target_domain = str(target_domain or "").strip().lower().rstrip(".")
    normalized_ips = sorted({str(ip).strip() for ip in (ips or []) if str(ip).strip()})

    def is_same_or_subdomain(name, suffix):
        return bool(name and suffix and (name == suffix or name.endswith("." + suffix)))

    is_target_site = is_same_or_subdomain(hostname, target_domain)
    known_brand_alias = any(
        target_domain == source_domain
        and any(is_same_or_subdomain(hostname, alias) for alias in aliases)
        for source_domain, aliases in _DIAGNOSTIC_BRAND_ALIASES.items()
    )
    system_background = any(
        is_same_or_subdomain(hostname, suffix)
        for suffix in _DIAGNOSTIC_BACKGROUND_SUFFIXES
    ) or any(
        is_same_or_subdomain(hostname, zone) for zone in _DIAGNOSTIC_BACKGROUND_ZONES
    )

    def close_in_time(left, right):
        # Syslog supplies time-of-day only; account for the midnight boundary.
        delta = abs(int(left) - int(right)) % 86400
        delta = min(delta, 86400 - delta)
        return delta <= relation_window_seconds

    valid_query_times = [
        int(value) for value in (query_times or []) if value is not None
    ]
    valid_target_times = [
        int(value) for value in (target_times or []) if value is not None
    ]
    time_related = bool(
        not is_target_site
        and not known_brand_alias
        and not system_background
        and valid_query_times
        and valid_target_times
        and any(
            close_in_time(query_time, target_time)
            for query_time in valid_query_times
            for target_time in valid_target_times
        )
    )

    if is_target_site:
        category = "target_site"
        role = "Ресурс целевого домена"
    elif system_background:
        category = "background"
        role = "Системный/служебный DNS-запрос — связь с целевым сайтом не установлена"
    elif known_brand_alias:
        category = "external_candidate"
        role = "Домен пространства бренда 2GIS (.2gis.com); зависимость не подтверждена"
    elif time_related:
        category = "external_candidate"
        role = (
            "Внешний кандидат — DNS-запрос в пределах 5 секунд; связь не подтверждена"
        )
    else:
        category = "background"
        role = "Фоновый DNS-запрос — близкой временной связи с целевым сайтом нет"

    direct_flags = [ip in direct_ips for ip in normalized_ips]
    if not normalized_ips:
        route = "unknown"
        route_basis = "Нет IPv4-адреса A-ответа в диагностике"
    elif all(direct_flags):
        route = "wan"
        route_basis = "Все IPv4-адреса входят в MAXVPN_DIRECT"
    elif any(direct_flags):
        route = "mixed"
        route_basis = "Часть IPv4-адресов входит в MAXVPN_DIRECT, часть — нет"
    else:
        route = "vpn"
        route_basis = "IPv4-адреса вне MAXVPN_DIRECT; по текущей политике ожидается VPN"

    normalized_rules = [str(rule).strip().lower().rstrip(".") for rule in (rules or [])]
    rule_covered = any(
        hostname == rule or hostname.endswith("." + rule) for rule in normalized_rules
    )
    # Time-correlated third-party domains are shown as candidates, but only
    # target-site and known-brand domains can be selected for DIRECT.
    selection_allowed = bool(
        (is_target_site or known_brand_alias)
        and normalized_ips
        and route == "vpn"
        and not rule_covered
    )
    return {
        "hostname": hostname,
        "ips": normalized_ips,
        "route": route,
        "route_basis": route_basis,
        "direct": route == "wan",
        "covered_by_rule": rule_covered,
        "same_site": is_target_site,
        "category": category,
        "role": role,
        "selection_allowed": selection_allowed,
        "candidate_for_direct": selection_allowed,
    }


def _diagnostic_brand_alias(hostname, domain):
    hostname = str(hostname or "").lower().rstrip(".")
    domain = str(domain or "").lower().rstrip(".")
    return any(
        hostname == alias or hostname.endswith("." + alias)
        for alias in _DIAGNOSTIC_BRAND_ALIASES.get(domain, ())
    )


def _diagnostic_candidate_related(hostname, domain):
    hostname = str(hostname or "").lower().rstrip(".")
    domain = str(domain or "").lower().rstrip(".")
    same_site = hostname == domain or hostname.endswith("." + domain)
    return same_site or _diagnostic_brand_alias(hostname, domain)


def _diagnostic_validate_direct_candidate(token, hostname):
    """Validate a diagnostic-originated DIRECT rule against one finished session."""
    session = DIAGNOSTICS.get(str(token or ""))
    if session is None:
        raise ValueError("diagnostic session not found")
    if time.time() < float(session.get("expires_at", 0)):
        raise ValueError("diagnostic session is still running")

    hostname = validate_target("domain", str(hostname or ""))
    if not _diagnostic_candidate_related(hostname, session.get("domain", "")):
        raise ValueError("hostname is not related to the diagnosed site")

    observations = session.get("observed_resources") or {}
    resource = observations.get(hostname)
    if not isinstance(resource, dict):
        raise ValueError("hostname was not observed in this diagnostic session")

    ipv4s = set()
    for value in resource.get("ips", []):
        try:
            address = ipaddress.ip_address(str(value))
        except ValueError:
            continue
        if isinstance(address, ipaddress.IPv4Address):
            ipv4s.add(str(address))
    if not ipv4s:
        raise ValueError("diagnostic candidate has no observed IPv4 address")

    # If any observed address is already in the DIRECT ipset, the expected route
    # is ambiguous; never create a diagnostic rule for that hostname.
    if ipv4s.intersection(_diagnostic_direct_ips()):
        raise ValueError("diagnostic candidate has an ambiguous DIRECT route")
    if _diagnostic_rule_covers(hostname, _diagnostic_domain_rules()):
        raise ValueError("hostname is already covered by a DIRECT domain rule")
    return hostname, session


def _diagnostic_create_direct_rule(token, hostname):
    hostname, session = _diagnostic_validate_direct_candidate(token, hostname)
    comment = validate_comment(f"Диагностика: {session['domain']}")
    c = db()
    try:
        existing = c.execute(
            "SELECT id FROM rules WHERE target_type='domain' AND target=? LIMIT 1",
            (hostname,),
        ).fetchone()
        if existing:
            raise ValueError("already exists")
        max_priority = c.execute(
            "SELECT COALESCE(MAX(priority), 0) FROM rules"
        ).fetchone()[0]
        priority = int(max_priority) + 10
        cur = c.execute(
            "INSERT INTO rules(target_type,target,action,priority,address_family,enabled,created_at,comment) VALUES(?,?,?,?,?,?,?,?)",
            (
                "domain",
                hostname,
                "direct",
                priority,
                "any",
                1,
                int(time.time()),
                comment,
            ),
        )
        c.commit()
        row = c.execute("SELECT * FROM rules WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row) | {"enabled": bool(row["enabled"])}
    finally:
        c.close()


def diagnostic_start(domain, client_ip="", duration_seconds=None):
    domain = _normalize_diagnostic_domain(domain)

    try:
        duration = int(duration_seconds or DIAGNOSTIC_DEFAULT_SECONDS)
    except (TypeError, ValueError):
        duration = DIAGNOSTIC_DEFAULT_SECONDS

    duration = max(10, min(60, duration))

    token = uuid.uuid4().hex
    now = time.time()

    DIAGNOSTICS[token] = {
        "domain": domain,
        "requested_client_ip": str(client_ip or "").strip(),
        "resolved_client_ip": str(client_ip or "").strip(),
        "started_at": now,
        "expires_at": now + duration,
        "cursor": _diagnostic_log_cursor(),
        "observed_resources": {},
        "parser_state": {
            "transactions": {},
            "selected_client_ip": str(client_ip or "").strip(),
        },
    }

    return {
        "token": token,
        "domain": domain,
        "duration_seconds": duration,
        "started_at": int(now),
        "expires_at": int(now + duration),
        "client_ip": str(client_ip or "").strip() or None,
    }


def diagnostic_result(token):
    session = DIAGNOSTICS.get(token)
    if session is None:
        raise ValueError("diagnostic session not found")

    data, new_cursor, reset = _diagnostic_read_delta(session["cursor"])
    session["cursor"] = new_cursor

    requested_client_ip = str(session.get("requested_client_ip") or "").strip()
    resolved_client_ip = str(session.get("resolved_client_ip") or "").strip()
    effective_client_ip = requested_client_ip or resolved_client_ip
    parser_state = session.setdefault(
        "parser_state",
        {
            "transactions": {},
            "selected_client_ip": effective_client_ip,
        },
    )
    client_ip, new_resources = _diagnostic_parse(
        data,
        effective_client_ip,
        parser_state=parser_state,
        reset=reset,
    )
    if not effective_client_ip and client_ip:
        effective_client_ip = str(client_ip).strip()
        session["resolved_client_ip"] = effective_client_ip

    # Retain each hostname, IP and query timestamp across the incremental polls.
    accumulated = session.setdefault("observed_resources", {})
    for resource in new_resources:
        hostname = str(resource.get("hostname") or "").strip().lower().rstrip(".")
        if not hostname:
            continue
        entry = accumulated.setdefault(
            hostname,
            {"hostname": hostname, "ips": [], "queries": 0, "query_times": []},
        )
        for address in resource.get("ips") or []:
            address = str(address).strip()
            if address and address not in entry["ips"]:
                entry["ips"].append(address)
        entry["queries"] += int(resource.get("queries") or 0)
        for query_time in resource.get("query_times") or []:
            query_time = int(query_time)
            if query_time not in entry["query_times"]:
                entry["query_times"].append(query_time)
        entry["query_times"].sort()

    domain = str(session.get("domain") or "").strip().lower().rstrip(".")
    target_times = set()
    for hostname, entry in accumulated.items():
        if hostname == domain or hostname.endswith("." + domain):
            target_times.update(entry.get("query_times") or [])

    direct_ips = _diagnostic_direct_ips()
    rules = _diagnostic_domain_rules()
    now = time.time()
    finished = now >= float(session.get("expires_at", 0))

    enriched = []
    for entry in accumulated.values():
        item = _diagnostic_classify_resource(
            hostname=entry["hostname"],
            ips=entry["ips"],
            direct_ips=direct_ips,
            rules=rules,
            target_domain=domain,
            query_times=entry.get("query_times") or [],
            target_times=target_times,
            relation_window_seconds=5,
        )
        item["queries"] = int(entry.get("queries") or 0)
        item["query_times"] = sorted(entry.get("query_times") or [])
        item["candidate_eligible"] = bool(finished and item["candidate_for_direct"])
        enriched.append(item)

    category_order = {"target_site": 0, "external_candidate": 1, "background": 2}
    route_order = {"unknown": 0, "mixed": 1, "vpn": 2, "wan": 3}
    enriched.sort(
        key=lambda item: (
            category_order.get(item["category"], 9),
            route_order.get(item["route"], 9),
            -item["queries"],
            item["hostname"],
        )
    )

    observed = len(enriched)
    target_count = sum(1 for item in enriched if item["category"] == "target_site")
    candidate_count = sum(
        1 for item in enriched if item["category"] == "external_candidate"
    )
    background_count = sum(1 for item in enriched if item["category"] == "background")
    with_ip = sum(1 for item in enriched if item["ips"])
    without_ip = observed - with_ip
    direct_count = sum(1 for item in enriched if item["route"] == "wan")
    vpn_count = sum(1 for item in enriched if item["route"] == "vpn")
    mixed_count = sum(1 for item in enriched if item["route"] == "mixed")
    unknown_count = sum(1 for item in enriched if item["route"] == "unknown")

    return {
        "token": token,
        "domain": domain,
        "client_ip": effective_client_ip or client_ip or None,
        "running": not finished,
        "finished": finished,
        "reset": reset,
        "remaining_seconds": max(0, int(session["expires_at"] - now)),
        "resources": enriched,
        "summary": {
            "observed": observed,
            "target_site": target_count,
            "external_candidates": candidate_count,
            "background": background_count,
            "with_ip": with_ip,
            "without_ip": without_ip,
            "direct": direct_count,
            "vpn": vpn_count,
            "mixed": mixed_count,
            "unknown": unknown_count,
            "unknown_route": unknown_count,
            "missing_direct": vpn_count,
        },
    }


def apply_routing():
    with routing_lock():
        return _apply_routing()


def _apply_routing():
    c = db()
    rows = c.execute("SELECT * FROM rules ORDER BY priority,id").fetchall()
    c.close()
    # Record the exact snapshot used below; edits during apply stay pending.
    applied_hash = rule_config_hash(rows)
    rows = [r for r in rows if r["enabled"]]
    domains = [r["target"] for r in rows if r["target_type"] == "domain"]
    cidrs = [r["target"] for r in rows if r["target_type"] == "cidr"]

    discover_network()
    if not isinstance(WAN_IF, str) or not WAN_IF.strip():
        raise RuntimeError("WAN interface not detected")
    try:
        gateway = ipaddress.IPv4Address(WAN_GW)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("WAN gateway not detected or invalid") from exc
    if gateway.is_unspecified or gateway.is_multicast or gateway.is_loopback:
        raise RuntimeError(f"WAN gateway is not a usable IPv4 address: {WAN_GW}")

    # Validate WAN readiness before touching ipsets, mangle, policy routes or dnsmasq.
    ensure_direct_path()
    update_dnsmasq_domains(domains)
    rebuild_static_ipsets(cidrs)
    shell("/etc/init.d/dnsmasq reload")
    set_applied_hash(applied_hash)
    return routing_info()


def vpn_action(action):
    scripts = {
        "start": "/usr/bin/vpn-lan-on",
        "stop": "/usr/bin/vpn-lan-off",
    }

    script = scripts.get(action)
    if script is None:
        raise ValueError(f"unsupported VPN action: {action}")

    p = run([script], check=False)
    time.sleep(1)

    mode_path = Path("/etc/maxvpn/runtime-mode")
    traffic_mode = mode_path.read_text().strip() if mode_path.exists() else None

    return {
        "action": action,
        "returncode": p.returncode,
        "stdout": p.stdout.strip(),
        "stderr": p.stderr.strip(),
        "traffic_mode": traffic_mode,
        "vpn": vpn_info(),
    }


IMPORT_MAX_BYTES = 1024 * 1024


def _import_type(value):
    value = str(value or "").strip().lower()

    aliases = {
        "domain": "domain",
        "домен": "domain",
        "host": "domain",
        "hostname": "domain",
        "fqdn": "domain",
        "cidr": "cidr",
        "ip": "cidr",
        "ip/cidr": "cidr",
        "address": "cidr",
        "ipv4": "cidr",
        "ipv4/cidr": "cidr",
    }

    return aliases.get(value)


def _infer_import_type(resource):
    try:
        network = ip_network(resource, strict=False)
        if network.version in (4, 6):
            return "cidr"
    except ValueError:
        pass

    return "domain"


def _normalize_import_resource(resource, target_type):
    resource = str(resource or "").strip()

    if not resource:
        raise ValueError("Пустой ресурс")

    target_type = target_type or _infer_import_type(resource)

    if target_type not in ("domain", "cidr"):
        raise ValueError("Тип ресурса должен быть domain или cidr")

    normalized = validate_target(target_type, resource)

    if target_type == "cidr":
        network = ip_network(normalized, strict=False)
        if network.version != 4:
            raise ValueError("IPv6 CIDR пока не поддерживается")
        address_family = "ipv4"
    else:
        address_family = "any"

    return (
        normalized,
        target_type,
        address_family,
    )


def _parse_import_source(filename, content):
    if len(content.encode("utf-8")) > IMPORT_MAX_BYTES:
        raise ValueError(
            f"import file is too large; maximum is {IMPORT_MAX_BYTES} bytes"
        )

    records = []
    is_csv = str(filename or "").lower().endswith(".csv")

    if is_csv:
        sample = content[:8192]

        try:
            dialect = csv.Sniffer().sniff(
                sample,
                delimiters=",;\t",
            )
        except csv.Error:
            dialect = csv.excel

        rows = list(
            csv.reader(
                io.StringIO(content),
                dialect,
            )
        )

        nonempty = [
            (line, row)
            for line, row in enumerate(rows, start=1)
            if any(str(cell).strip() for cell in row)
        ]

        if not nonempty:
            return records

        def header_name(value):
            return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")

        resource_names = {
            "resource",
            "target",
            "domain",
            "host",
            "address",
            "ip",
            "url",
            "ресурс",
            "домен",
            "адрес",
        }

        comment_names = {
            "comment",
            "comments",
            "note",
            "description",
            "комментарий",
            "комментарий_к_правилу",
            "описание",
        }

        type_names = {
            "type",
            "target_type",
            "тип",
        }

        first_line, first_row = nonempty[0]
        normalized_header = {
            index: header_name(value) for index, value in enumerate(first_row)
        }

        has_header = any(
            value in resource_names or value in comment_names or value in type_names
            for value in normalized_header.values()
        )

        if has_header:
            resource_index = next(
                (
                    index
                    for index, value in normalized_header.items()
                    if value in resource_names
                ),
                0,
            )

            comment_index = next(
                (
                    index
                    for index, value in normalized_header.items()
                    if value in comment_names
                ),
                None,
            )

            type_index = next(
                (
                    index
                    for index, value in normalized_header.items()
                    if value in type_names
                ),
                None,
            )

            data_rows = nonempty[1:]
        else:
            resource_index = 0

            comment_index = 1 if len(first_row) > 1 else None
            type_index = None

            if len(first_row) > 1:
                second = str(first_row[1]).strip().lower()

                if second in {
                    "domain",
                    "cidr",
                    "ip",
                    "ipv4",
                    "ipv6",
                }:
                    type_index = 1
                    comment_index = 2 if len(first_row) > 2 else None

            if type_index is None and len(first_row) > 2:
                third = str(first_row[2]).strip().lower()

                if third in {
                    "domain",
                    "cidr",
                    "ip",
                    "ipv4",
                    "ipv6",
                }:
                    type_index = 2

            data_rows = nonempty

        for line, row in data_rows:
            if not row:
                continue

            resource = row[resource_index].strip() if resource_index < len(row) else ""

            requested_type = (
                row[type_index].strip()
                if type_index is not None and type_index < len(row)
                else ""
            )

            comment = (
                row[comment_index].strip()
                if comment_index is not None and comment_index < len(row)
                else ""
            )

            if not resource:
                continue

            records.append(
                (
                    line,
                    resource,
                    requested_type,
                    comment,
                )
            )

    else:
        for line, raw in enumerate(
            content.splitlines(),
            start=1,
        ):
            value = raw.strip()

            if not value:
                continue

            if value.startswith("#"):
                continue

            if value.startswith("//"):
                continue

            # TXT:
            # resource<TAB>comment
            # resource;comment
            comment = ""

            if "\t" in value:
                value, comment = value.split("\t", 1)
                value = value.strip()
                comment = comment.strip()
            elif ";" in value and not value.startswith(";"):
                value, comment = value.split(";", 1)
                value = value.strip()
                comment = comment.strip()
            elif value.startswith(";"):
                continue

            if not value:
                continue

            records.append(
                (
                    line,
                    value,
                    "",
                    comment,
                )
            )

    return records


def _smart_routing_import_plan(filename, content):
    records = _parse_import_source(
        filename,
        content,
    )

    c = db()

    existing_rows = c.execute("SELECT target_type, target FROM rules").fetchall()

    c.close()

    existing = {
        (
            str(row["target_type"]),
            str(row["target"]).strip().lower().rstrip("."),
        )
        for row in existing_rows
    }

    planned = set()
    items = []

    for line, resource, requested_type, comment in records:
        raw_comment = comment

        try:
            comment = validate_comment(comment)
            target_type = _import_type(requested_type)

            (
                normalized,
                target_type,
                address_family,
            ) = _normalize_import_resource(
                resource,
                target_type,
            )

            compare_target = normalized.strip().lower().rstrip(".")

            key = (
                target_type,
                compare_target,
            )

            if key in planned:
                status = "duplicate"
                error = None
            elif key in existing:
                status = "already_exists"
                error = None
            else:
                status = "valid"
                error = None
                planned.add(key)

            items.append(
                {
                    "line": line,
                    "resource": normalized,
                    "target_type": target_type,
                    "address_family": address_family,
                    "comment": comment,
                    "status": status,
                    "error": error,
                }
            )

        except Exception as exc:
            items.append(
                {
                    "line": line,
                    "resource": resource,
                    "target_type": None,
                    "address_family": None,
                    "comment": raw_comment,
                    "status": "invalid",
                    "error": str(exc),
                }
            )

    return items


def smart_routing_import_preview(filename, content):
    items = _smart_routing_import_plan(
        filename,
        content,
    )

    return {
        "filename": filename,
        "total": len(items),
        "new": sum(item["status"] == "valid" for item in items),
        "duplicates": sum(item["status"] == "duplicate" for item in items),
        "already_exists": sum(item["status"] == "already_exists" for item in items),
        "invalid": sum(item["status"] == "invalid" for item in items),
        "items": items,
    }


def smart_routing_import(filename, content):
    items = _smart_routing_import_plan(
        filename,
        content,
    )

    valid_items = [item for item in items if item["status"] == "valid"]

    c = db()

    max_priority = c.execute("SELECT COALESCE(MAX(priority), 0) FROM rules").fetchone()[
        0
    ]

    created = []

    try:
        priority = int(max_priority) + 10

        for item in valid_items:
            cur = c.execute(
                """
                INSERT INTO rules(
                    target_type,
                    target,
                    action,
                    priority,
                    address_family,
                    enabled,
                    created_at,
                    comment
                )
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    item["target_type"],
                    item["resource"],
                    "direct",
                    priority,
                    item["address_family"],
                    1,
                    int(time.time()),
                    item["comment"],
                ),
            )

            row = c.execute(
                "SELECT * FROM rules WHERE id=?",
                (cur.lastrowid,),
            ).fetchone()

            created.append(dict(row) | {"enabled": bool(row["enabled"])})

            priority += 10

        c.commit()

    except Exception:
        c.rollback()
        raise

    finally:
        c.close()

    return {
        "filename": filename,
        "requested": len(items),
        "added": len(created),
        "already_exists": sum(item["status"] == "already_exists" for item in items),
        "duplicates": sum(item["status"] == "duplicate" for item in items),
        "invalid": sum(item["status"] == "invalid" for item in items),
        "rules": created,
    }


def _route_test_resolve_addresses(rule):
    """Resolve a rule target to representative IPv4 destination addresses."""
    target_type = str(rule.get("target_type") or "").strip().lower()
    target = str(rule.get("target") or "").strip()

    if target_type == "cidr":
        try:
            network = ip_network(target, strict=False)
        except ValueError:
            return []
        if network.version != 4:
            return []
        if network.num_addresses == 1:
            return [str(network.network_address)]
        return [str(network.network_address + 1)]

    if target_type != "domain" or not target:
        return []

    response = run(["nslookup", target, "127.0.0.1"], check=False)
    addresses = []
    for line in (response.stdout or "").splitlines():
        match = re.search(r"\bAddress(?:\s+\d+)?\s*:\s*([0-9a-fA-F:.]+)", line)
        if not match:
            continue
        try:
            address = ipaddress.ip_address(match.group(1))
        except ValueError:
            continue
        if address.version == 4 and not address.is_loopback:
            addresses.append(str(address))
    return list(dict.fromkeys(addresses))


def _route_test_ipset(name, address):
    listing = run(["ipset", "list", name], check=False)
    if listing.returncode != 0:
        raw = (listing.stderr or listing.stdout or f"ipset {name} unavailable").strip()
        return {"ok": False, "available": False, "raw": raw}

    probe = run(["ipset", "test", name, address], check=False)
    raw = (probe.stdout or probe.stderr or "").strip()
    if not raw:
        raw = "member" if probe.returncode == 0 else "not a member"
    return {
        "ok": probe.returncode == 0,
        "available": True,
        "raw": raw,
    }


def _route_test_lookup(address, marked, lan_policy_present=False):
    """Check DIRECT via fwmark, and model ordinary LAN routing via table 100."""
    if marked:
        command = ["ip", "-4", "route", "get", address, "mark", "0x64"]
        response = run(command, check=False)
        raw = (response.stdout or response.stderr or "").strip()
        dev_match = re.search(r"(?:^|\s)dev\s+(\S+)", raw)
        via_match = re.search(r"(?:^|\s)via\s+(\S+)", raw)
        table_match = re.search(r"(?:^|\s)table\s+(\S+)", raw)
        mark_match = re.search(r"(?:^|\s)mark\s+0x0*64(?:/0xff)?(?:\s|$)", raw)

        ok = bool(
            response.returncode == 0
            and table_match
            and table_match.group(1) == str(TABLE)
            and mark_match
        )
        return {
            "ok": ok,
            "raw": raw or "marked route lookup failed",
            "dev": dev_match.group(1) if dev_match else None,
            "via": via_match.group(1) if via_match else None,
            "command": command,
            "returncode": int(response.returncode),
            "probe_client_ip": None,
            "probe_client_state": None,
        }

    # A local `ip route get ADDRESS` uses the router's own routing context.
    # It is not a reliable substitute for a forwarded packet from br-lan.
    command = ["ip", "-4", "route", "show", "table", "100"]

    if not lan_policy_present:
        return {
            "ok": False,
            "raw": (
                "Cannot confirm the unmarked LAN route: "
                "policy 'iif br-lan lookup 100' was not detected."
            ),
            "dev": None,
            "via": None,
            "command": command,
            "returncode": 2,
            "probe_client_ip": None,
            "probe_client_state": None,
        }

    response = run(command, check=False)
    output = (response.stdout or "").strip()

    def failed_lookup(message, returncode):
        return {
            "ok": False,
            "raw": message,
            "dev": None,
            "via": None,
            "command": command,
            "returncode": int(returncode),
            "probe_client_ip": None,
            "probe_client_state": None,
        }

    if response.returncode != 0:
        return failed_lookup(
            output or response.stderr or "Cannot read routing table 100.",
            response.returncode,
        )

    try:
        destination = ipaddress.ip_address(address)
    except ValueError:
        return failed_lookup(f"Invalid destination address: {address}", 2)

    if destination.version != 4:
        return failed_lookup("Only IPv4 route-table modeling is supported.", 2)

    # Include special route types in longest-prefix selection, but never
    # describe a blocked or thrown route as a confirmed VPN route.
    special_types = {
        "blackhole",
        "unreachable",
        "prohibit",
        "throw",
        "local",
        "broadcast",
        "multicast",
        "nat",
        "anycast",
    }
    candidates = []

    for line_number, line in enumerate(output.splitlines()):
        fields = line.split()
        if not fields:
            continue

        route_type = "unicast"
        destination_index = 0
        if fields[0] in special_types:
            route_type = fields[0]
            destination_index = 1

        if destination_index >= len(fields):
            continue

        prefix = fields[destination_index]
        try:
            network = (
                ipaddress.ip_network("0.0.0.0/0")
                if prefix == "default"
                else ipaddress.ip_network(prefix, strict=False)
            )
        except ValueError:
            continue

        if network.version != 4 or destination not in network:
            continue

        metric_match = re.search(r"(?:^|\s)metric\s+(\d+)(?:\s|$)", line)
        metric = int(metric_match.group(1)) if metric_match else 0

        # Prefer longest prefix, then lower metric, then stable output order.
        candidates.append((network.prefixlen, -metric, -line_number, line, route_type))

    if not candidates:
        return failed_lookup(
            f"No matching IPv4 route found in table 100 for {address}.",
            2,
        )

    _, _, _, selected_line, route_type = max(candidates)
    raw = f"{address} {selected_line} table 100 (LAN policy: iif {LAN_IF})"
    dev_match = re.search(r"(?:^|\s)dev\s+(\S+)", selected_line)
    via_match = re.search(r"(?:^|\s)via\s+(\S+)", selected_line)

    blocked_types = {"blackhole", "unreachable", "prohibit", "throw"}
    ok = bool(route_type not in blocked_types and (dev_match or via_match))

    return {
        "ok": ok,
        "raw": raw,
        "dev": dev_match.group(1) if dev_match else None,
        "via": via_match.group(1) if via_match else None,
        "command": command,
        "returncode": 0 if ok else 2,
        "probe_client_ip": None,
        "probe_client_state": "modeled from LAN policy table 100" if ok else None,
    }


def route_test_rule(rule_id):
    """Read-only route test for a stored Smart Routing rule."""
    connection = db()
    try:
        row = connection.execute(
            "SELECT * FROM rules WHERE id = ?", (int(rule_id),)
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None

    rule = dict(row)
    rule["enabled"] = bool(rule.get("enabled"))
    rule["comment"] = str(rule.get("comment") or "")
    rule_payload = {
        key: rule.get(key)
        for key in (
            "id",
            "target_type",
            "target",
            "action",
            "priority",
            "address_family",
            "enabled",
            "comment",
        )
    }
    rule_payload["id"] = int(rule_payload["id"])
    rule_payload["priority"] = int(rule_payload["priority"] or 0)

    runtime_state = routing_info()
    lan_policy_present = bool(
        re.search(
            r"\biif\s+br-lan\s+lookup\s+100\b", str(runtime_state.get("ip_rule") or "")
        )
    )
    config_hash = str(runtime_state.get("config_hash") or rule_config_hash())
    applied_hash = str(
        runtime_state.get("applied_config_hash") or get_applied_hash() or ""
    )
    config_dirty = bool(
        runtime_state.get("config_dirty")
        or (applied_hash and config_hash != applied_hash)
    )
    config_applied = bool(
        applied_hash and config_hash == applied_hash and not config_dirty
    )

    addresses = _route_test_resolve_addresses(rule)
    destinations = []
    for address in addresses:
        direct_ipset = _route_test_ipset(DIRECT_IPSET, address)
        static_ipset = _route_test_ipset(STATIC_IPSET, address)
        static_net_ipset = _route_test_ipset(STATIC_NET_IPSET, address)
        marked_route = _route_test_lookup(address, marked=True)
        unmarked_route = _route_test_lookup(
            address, marked=False, lan_policy_present=lan_policy_present
        )

        is_direct_member = any(
            item["available"] and item["ok"]
            for item in (direct_ipset, static_ipset, static_net_ipset)
        )
        unmarked_is_vpn = bool(
            unmarked_route["ok"]
            and unmarked_route["dev"]
            and unmarked_route["dev"] not in {WAN_IF, LAN_IF, "lo"}
        )

        if not rule["enabled"]:
            decision = "disabled"
            reasons = ["Правило выключено."]
        elif not config_applied:
            decision = "not_applied"
            reasons = [
                "Текущая конфигурация Smart Routing не подтверждена как применённая."
            ]
        elif is_direct_member and marked_route["ok"]:
            decision = "direct"
            reasons = [
                "Адрес найден в одном из DIRECT IP-set.",
                "Маршрут с mark 0x64 выбирает table 200.",
            ]
        elif (
            not is_direct_member
            and unmarked_route["returncode"] == 0
            and unmarked_is_vpn
        ):
            decision = "vpn"
            reasons = [
                "Адрес отсутствует в DIRECT IP-set.",
                "Обычный маршрут выбирает VPN-маршрут.",
            ]
        else:
            decision = "unknown"
            reasons = [
                "Не удалось подтвердить ожидаемый DIRECT-маршрут по IP-set "
                "и route lookup."
            ]

        destinations.append(
            {
                "ip": address,
                "family": "ipv4",
                "direct_ipset": direct_ipset,
                "static_ipset": static_ipset,
                "static_net_ipset": static_net_ipset,
                "marked_route": marked_route,
                "unmarked_route": unmarked_route,
                "decision": decision,
                "reason": reasons,
            }
        )

    decisions = [item["decision"] for item in destinations]
    if not rule["enabled"]:
        overall = "disabled"
    elif not config_applied:
        overall = "not_applied"
    elif not decisions:
        overall = "unknown"
    elif all(item == "direct" for item in decisions):
        overall = "direct"
    elif all(item == "vpn" for item in decisions):
        overall = "vpn"
    else:
        overall = "unknown"

    vpn_interface = VPN_IF
    for item in destinations:
        dev = item["unmarked_route"]["dev"]
        if dev and dev not in {WAN_IF, LAN_IF, "lo"}:
            vpn_interface = dev
            break

    return {
        "rule": rule_payload,
        "configuration": {
            "config_hash": config_hash,
            "applied_config_hash": applied_hash,
            "config_dirty": config_dirty,
            "applied": config_applied,
        },
        "resolution": {"ok": bool(addresses), "addresses": addresses},
        "runtime": {
            "direct_ipset": bool(runtime_state.get("direct_ipset")),
            "static_ipset": bool(runtime_state.get("static_ipset")),
            "static_net_ipset": bool(runtime_state.get("static_net_ipset")),
            "mangle_direct": bool(runtime_state.get("mangle_direct")),
            "mangle_static": bool(runtime_state.get("mangle_static")),
            "mangle_static_net": bool(runtime_state.get("mangle_static_net")),
            "mangle_direct_count": int(runtime_state.get("mangle_direct_count") or 0),
            "mangle_static_count": int(runtime_state.get("mangle_static_count") or 0),
            "mangle_static_net_count": int(
                runtime_state.get("mangle_static_net_count") or 0
            ),
            "policy_rules": str(runtime_state.get("ip_rule") or ""),
            "table_200": str(runtime_state.get("table_200") or ""),
            "wan_interface": str(runtime_state.get("wan_interface") or WAN_IF),
            "wan_gateway": str(runtime_state.get("wan_gateway") or WAN_GW),
            "vpn_interface": str(vpn_interface),
        },
        "overall": overall,
        "destinations": destinations,
        "summary": {
            "resolved": len(destinations),
            "direct": decisions.count("direct"),
            "vpn": decisions.count("vpn"),
            "not_applied": decisions.count("not_applied"),
            "disabled": decisions.count("disabled"),
            "unknown": decisions.count("unknown"),
        },
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "MaxVPN-Appliance/5.0"

    def log_message(self, *_):
        pass

    def send_json(self, code, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, code, message):
        self.send_json(code, {"error": message})

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 512 * 1024:
            raise ValueError("request too large")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/health":
                return self.send_json(
                    200,
                    {
                        "status": "ok",
                        "service": "maxvpn-appliance",
                        "phase": 5.0,
                        "version": "5.0",
                    },
                )
            if path == "/api/appliance/v1/status":
                return self.send_json(200, status_runtime())
            if path == "/api/appliance/v1/vpn":
                return self.send_json(200, vpn_info())
            if path == "/api/appliance/v1/vpn/mode":
                return self.send_json(200, {"mode": VLESS_CONTROL._read_mode()})
            if path == "/api/appliance/v1/vless/delays/history":
                return self.send_json(200, VLESS_CONTROL.get_delay_history())
            if path == "/api/appliance/v1/vless/selection-history":
                return self.send_json(200, _vless_selection_history_payload())
            if path == "/api/appliance/v1/vless":
                return self.send_json(200, VLESS_CONTROL.get_state())
            m = re.fullmatch(r"/api/appliance/v1/routing/diagnostics/([a-f0-9]+)", path)
            if m:
                return self.send_json(200, diagnostic_result(m.group(1)))
            if path == "/api/appliance/v1/routing":
                return self.send_json(
                    200, {"rules": list_rules(), "runtime": routing_info()}
                )
            if path == "/api/appliance/v1/routing/rules":
                return self.send_json(200, list_rules())
            m = re.fullmatch(r"/api/appliance/v1/routing/rules/(\d+)", path)
            if m:
                rule_id = int(m.group(1))
                c = db()
                row = c.execute("SELECT * FROM rules WHERE id=?", (rule_id,)).fetchone()
                c.close()
                if row is None:
                    return self.send_error_json(404, "rule not found")
                return self.send_json(
                    200, dict(row) | {"enabled": bool(row["enabled"])}
                )
            return self.send_error_json(404, "not found")
        except VlessControlError as e:
            return self.send_error_json(503, str(e))
        except Exception as e:
            return self.send_error_json(500, str(e))

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            route_test_match = re.fullmatch(
                r"/api/appliance/v1/routing/rules/(\d+)/test", path
            )
            if route_test_match:
                route_result = route_test_rule(int(route_test_match.group(1)))
                if route_result is None:
                    return self.send_error_json(404, "rule not found")
                return self.send_json(200, route_result)
            if path == "/api/appliance/v1/vpn/start":
                return self.send_json(200, vpn_action("start"))
            if path == "/api/appliance/v1/vpn/stop":
                return self.send_json(200, vpn_action("stop"))
            if path == "/api/appliance/v1/vpn/mode":
                data = self.read_json()
                return self.send_json(200, VLESS_CONTROL.set_mode(data.get("mode")))
            if path == "/api/appliance/v1/vless/import":
                data = self.read_json()
                return self.send_json(200, VLESS_CONTROL.import_profiles(data))
            if path == "/api/appliance/v1/vless/settings":
                data = self.read_json()
                return self.send_json(200, VLESS_CONTROL.update_settings(data))
            if path == "/api/appliance/v1/vless/prepare":
                return self.send_json(200, VLESS_CONTROL.apply_config(start=False))
            if path == "/api/appliance/v1/vless/apply":
                return self.send_json(200, VLESS_CONTROL.apply_config(start=True))
            if path == "/api/appliance/v1/vless/start":
                return self.send_json(200, VLESS_CONTROL.start())
            if path == "/api/appliance/v1/vless/stop":
                return self.send_json(200, VLESS_CONTROL.stop())
            if path == "/api/appliance/v1/vless/select":
                data = self.read_json()
                return self.send_json(
                    200, VLESS_CONTROL.select_outbound(data.get("profile_id"))
                )
            if path == "/api/appliance/v1/vless/delays":
                return self.send_json(200, VLESS_CONTROL.test_delays())
            diagnostic_direct = re.fullmatch(
                r"/api/appliance/v1/routing/diagnostics/([0-9a-f]{32})/direct", path
            )
            if diagnostic_direct:
                data = self.read_json()
                try:
                    created = _diagnostic_create_direct_rule(
                        diagnostic_direct.group(1), data.get("target", "")
                    )
                except ValueError as exc:
                    if str(exc) == "already exists":
                        return self.send_error_json(409, "rule already exists")
                    raise
                return self.send_json(201, created)
            if path == "/api/appliance/v1/routing/diagnostics/start":
                data = self.read_json()
                return self.send_json(
                    201,
                    diagnostic_start(
                        data.get("domain", ""),
                        data.get("client_ip", ""),
                        data.get("duration_seconds"),
                    ),
                )
            if path == "/api/appliance/v1/routing/import/preview":
                data = self.read_json()

                result = smart_routing_import_preview(
                    data.get("filename", "import.txt"),
                    data.get("content", ""),
                )

                return self.send_json(
                    200,
                    result,
                )

            if path == "/api/appliance/v1/routing/import":
                data = self.read_json()

                result = smart_routing_import(
                    data.get("filename", "import.txt"),
                    data.get("content", ""),
                )

                return self.send_json(
                    201,
                    result,
                )

            if path == "/api/appliance/v1/routing/rules":
                data = self.read_json()
                target_type = data.get("target_type", "")
                target = validate_target(target_type, data.get("target", ""))
                comment = validate_comment(data.get("comment", ""))
                c = db()
                if (
                    data.get("priority") is None
                    or str(data.get("priority")).strip() == ""
                ):
                    max_priority = c.execute(
                        "SELECT COALESCE(MAX(priority), 0) FROM rules"
                    ).fetchone()[0]
                    priority = int(max_priority) + 10
                else:
                    priority = int(data.get("priority"))
                    if priority < 1:
                        raise ValueError("priority must be positive")
                    existing = c.execute(
                        "SELECT id FROM rules WHERE priority=? LIMIT 1", (priority,)
                    ).fetchone()
                    if existing:
                        c.close()
                        raise ValueError(f"priority {priority} already exists")
                address_family = "ipv4" if target_type == "cidr" else "any"
                cur = c.execute(
                    "INSERT INTO rules(target_type,target,action,priority,address_family,enabled,created_at,comment) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        target_type,
                        target,
                        "direct",
                        priority,
                        address_family,
                        1,
                        int(time.time()),
                        comment,
                    ),
                )
                c.commit()
                row = c.execute(
                    "SELECT * FROM rules WHERE id=?", (cur.lastrowid,)
                ).fetchone()
                c.close()
                return self.send_json(
                    201, dict(row) | {"enabled": bool(row["enabled"])}
                )
            if path == "/api/appliance/v1/routing/apply":
                return self.send_json(
                    200, {"applied": True, "runtime": apply_routing()}
                )
            if path == "/api/appliance/v1/routing/presets/russia-direct":
                return self.send_json(
                    200,
                    {
                        "preset": "russia-direct",
                        "rules": list_rules(),
                        "applied": False,
                        "note": "Existing Russian DIRECT domains imported from dnsmasq; use Apply to synchronize runtime.",
                    },
                )
            return self.send_error_json(404, "not found")
        except sqlite3.IntegrityError:
            return self.send_error_json(409, "rule already exists")
        except VlessControlError as e:
            code = (
                422 if path.endswith("/import") or path.endswith("/settings") else 502
            )
            return self.send_error_json(code, str(e))
        except ValueError as e:
            return self.send_error_json(422, str(e))
        except Exception as e:
            return self.send_error_json(500, str(e))

    def do_PATCH(self):
        path = urlparse(self.path).path
        vless_match = re.fullmatch(r"/api/appliance/v1/vless/profiles/(\d+)", path)
        if vless_match:
            try:
                data = self.read_json()
                return self.send_json(
                    200, VLESS_CONTROL.update_profile(int(vless_match.group(1)), data)
                )
            except VlessControlError as e:
                return self.send_error_json(422, str(e))
            except Exception as e:
                return self.send_error_json(500, str(e))
        m = re.fullmatch(
            r"/api/appliance/v1/routing/rules/(\d+)", urlparse(self.path).path
        )
        if not m:
            return self.send_error_json(404, "not found")
        try:
            rule_id = int(m.group(1))
            data = self.read_json()
            fields = []
            values = []
            new_target_type = data.get("target_type")
            new_target = data.get("target")
            if new_target_type is not None or new_target is not None:
                c_current = db()
                current = c_current.execute(
                    "SELECT target_type,target FROM rules WHERE id=?", (rule_id,)
                ).fetchone()
                c_current.close()
                if current is None:
                    return self.send_error_json(404, "rule not found")
                effective_type = (
                    str(
                        new_target_type
                        if new_target_type is not None
                        else current["target_type"]
                    )
                    .strip()
                    .lower()
                )
                effective_target = str(
                    new_target if new_target is not None else current["target"]
                )
                normalized_target = validate_target(effective_type, effective_target)
                c_check = db()
                existing_target = c_check.execute(
                    "SELECT id FROM rules WHERE target=? AND id<>? LIMIT 1",
                    (normalized_target, rule_id),
                ).fetchone()
                c_check.close()
                if existing_target:
                    raise ValueError(
                        f"rule with target {normalized_target} already exists"
                    )
                fields.extend(["target_type=?", "target=?", "address_family=?"])
                values.extend(
                    [
                        effective_type,
                        normalized_target,
                        "ipv4" if effective_type == "cidr" else "any",
                    ]
                )
            if "enabled" in data:
                fields.append("enabled=?")
                values.append(1 if bool(data["enabled"]) else 0)
            if "comment" in data:
                fields.append("comment=?")
                values.append(validate_comment(data.get("comment")))
            if "priority" in data:
                priority = int(data["priority"])
                if priority < 1:
                    raise ValueError("priority must be positive")
                c_check = db()
                existing = c_check.execute(
                    "SELECT id FROM rules WHERE priority=? AND id<>? LIMIT 1",
                    (priority, rule_id),
                ).fetchone()
                c_check.close()
                if existing:
                    raise ValueError(f"priority {priority} already exists")
                fields.append("priority=?")
                values.append(priority)
            if not fields:
                raise ValueError("nothing to update")
            values.append(rule_id)
            c = db()
            cur = c.execute(f"UPDATE rules SET {', '.join(fields)} WHERE id=?", values)
            c.commit()
            if cur.rowcount == 0:
                c.close()
                return self.send_error_json(404, "rule not found")
            row = c.execute("SELECT * FROM rules WHERE id=?", (rule_id,)).fetchone()
            c.close()
            return self.send_json(200, dict(row) | {"enabled": bool(row["enabled"])})
        except ValueError as e:
            return self.send_error_json(422, str(e))
        except Exception as e:
            return self.send_error_json(500, str(e))

    def do_DELETE(self):
        path = urlparse(self.path).path
        vless_match = re.fullmatch(r"/api/appliance/v1/vless/profiles/(\d+)", path)
        if vless_match:
            try:
                return self.send_json(
                    200, VLESS_CONTROL.delete_profile(int(vless_match.group(1)))
                )
            except VlessControlError as e:
                return self.send_error_json(422, str(e))
            except Exception as e:
                return self.send_error_json(500, str(e))
        m = re.fullmatch(r"/api/appliance/v1/routing/rules/(\d+)", path)
        if not m:
            return self.send_error_json(404, "not found")
        try:
            rule_id = int(m.group(1))
            c = db()
            cur = c.execute("DELETE FROM rules WHERE id=?", (rule_id,))
            c.commit()
            c.close()
            if cur.rowcount == 0:
                return self.send_error_json(404, "rule not found")
            return self.send_json(200, {"deleted": True, "id": rule_id})
        except Exception as e:
            return self.send_error_json(500, str(e))


def main(argv=None):
    parser = argparse.ArgumentParser(description="MaxVPN Appliance")
    parser.add_argument(
        "--restore-routing",
        action="store_true",
        help="restore Smart Routing once, without starting the API or VLESS monitor",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=os.environ.get("MAXVPN_APPLIANCE_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.restore_routing:
        seed_rules()
        return restore_routing_exit_code()

    discover_network()
    seed_rules()
    ensure_applied_baseline()
    threading.Thread(
        target=_vless_selection_monitor_loop,
        name="maxvpn-vless-selection-monitor",
        daemon=True,
    ).start()
    threading.Thread(
        target=_vless_wan_fallback_loop,
        name="maxvpn-vless-wan-fallback",
        daemon=True,
    ).start()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
