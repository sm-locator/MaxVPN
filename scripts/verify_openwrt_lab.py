"""Exercise real OpenWrt forwarding in the serial-controlled, isolated QEMU lab.

This checks the supported plain VLESS transport against a local peer. It does
not certify AmneziaWG or REALITY, which require a suitably provisioned image.
"""

import argparse
import io
import json
import re
from pathlib import Path
import shlex
import socket
import struct
import sys
import tarfile
import uuid

from openwrt_lab import Lab

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def archive(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as output:
        for name, content in files.items():
            data = content.encode() if isinstance(content, str) else content
            info = tarfile.TarInfo(name.lstrip("/"))
            info.size = len(data)
            info.mode = 0o755 if not name.endswith(".json") else 0o600
            output.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def setup(lab):
    from backend.infrastructure.openwrt.openwrt_firewall_persistence import (
        OpenWrtFirewallPersistence,
    )
    from backend.infrastructure.openwrt.openwrt_vless_singbox_controller import (
        OpenWrtVlessSingBoxController,
    )
    from backend.models.vless_config import VlessServerConfig
    from backend.models.vpn_traffic_policy import VpnTrafficPolicy
    from backend.services.vless_singbox_config_renderer import (
        VlessSingBoxConfigRenderer,
    )

    identity = str(uuid.uuid4())
    commands = OpenWrtFirewallPersistence(None).build_install_commands(
        VpnTrafficPolicy(), start_watchdog=False
    )
    installer = (
        "#!/bin/sh\nset -e\n" + "\n".join(shlex.join(cmd) for cmd in commands) + "\n"
    )
    config = VlessSingBoxConfigRenderer().render(
        VlessServerConfig("isolated-lab", "198.18.0.1", 24443, identity)
    )
    files = {
        "/tmp/maxvpn-lab-install.sh": installer,
        "/etc/maxvpn/sing-box-vless.json": json.dumps(config),
        "/etc/init.d/maxvpn-sing-box": OpenWrtVlessSingBoxController.SERVICE_SCRIPT,
        "/opt/maxvpn-appliance/server.py": (
            ROOT / "appliance/maxvpn/server.py"
        ).read_bytes(),
        "/opt/maxvpn-appliance/vless_control.py": (
            ROOT / "appliance/maxvpn/vless_control.py"
        ).read_bytes(),
        "/etc/hotplug.d/iface/99-maxvpn-restore-routing": (
            ROOT / "appliance/maxvpn/hotplug.d/iface/99-maxvpn-restore-routing"
        ).read_bytes(),
        "/tmp/maxvpn-lab-seed.py": """import sys, time
sys.path.insert(0, '/opt/maxvpn-appliance')
import server
c = server.db()
c.execute('DELETE FROM rules')
c.execute("INSERT INTO rules(target_type,target,created_at) VALUES('cidr','203.0.113.20/32',?)", (int(time.time()),))
c.commit()
c.close()
server.apply_routing()
assert server.rule_config_hash() == server.get_applied_hash()
""",
    }
    lab.command(
        "router",
        "/etc/init.d/maxvpn-appliance stop; /etc/init.d/maxvpn-vless-watchdog stop; true",
    )
    lab.put("router", "/tmp/maxvpn-lab.tar.gz", archive(files))
    print(
        "Uploaded current routing/firewall/appliance sources with SHA-256 verification",
        flush=True,
    )
    lab.command(
        "router",
        "tar -xzf /tmp/maxvpn-lab.tar.gz -C / && (uci delete network.mgmt 2>/dev/null || true) && uci set network.@device[0].ports=eth0 && uci commit network && /etc/init.d/network restart && sleep 3",
        timeout=40,
    )
    lab.command("router", "sh /tmp/maxvpn-lab-install.sh", timeout=45)
    lab.command(
        "router",
        "uci set dhcp.maxvpn_direct=ipset && uci set dhcp.maxvpn_direct.name=MAXVPN_DIRECT && uci set dhcp.maxvpn_direct.match=dest_ip && uci set dhcp.maxvpn_direct.family=ipv4 && uci commit dhcp && python3 /tmp/maxvpn-lab-seed.py && /etc/init.d/maxvpn-sing-box enable && /etc/init.d/maxvpn-sing-box restart && sleep 2 && /usr/bin/vpn-lan-off",
        timeout=40,
    )
    print(
        "Installed final helpers and isolated DIRECT rule; router is in WAN mode",
        flush=True,
    )
    setup_peer(lab, identity)


def setup_peer(lab, identity=None):
    if identity is None:
        output = lab.command(
            "router",
            'python3 -c \'import json;print(json.load(open("/etc/maxvpn/sing-box-vless.json"))["outbounds"][0]["uuid"])\'',
        )
        identity = re.findall(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}", output)[
            -1
        ]
    peer = {
        "log": {"level": "info"},
        "inbounds": [
            {
                "type": "vless",
                "listen": "::",
                "listen_port": 24443,
                "users": [{"uuid": identity}],
            }
        ],
        "outbounds": [{"type": "direct", "tag": "direct"}],
    }
    lab.put("wan", "/tmp/maxvpn-peer.json", json.dumps(peer).encode())
    lab.command(
        "wan",
        "ip addr add 203.0.113.10/32 dev lo 2>/dev/null || true; ip addr add 203.0.113.20/32 dev lo 2>/dev/null || true; ip -6 addr add fd77:77:3::10/128 dev lo 2>/dev/null || true; echo LAB_OK > /www/lab.txt; /etc/init.d/uhttpd start; sing-box check -c /tmp/maxvpn-peer.json && (sing-box run -c /tmp/maxvpn-peer.json > /tmp/maxvpn-peer.log 2>&1 &)",
    )
    print(
        "Started local VLESS peer and HTTP destinations; no external uplink", flush=True
    )


def check(lab, label, command, node="client"):
    lab.command(node, command)
    print(f"PASS: {label}", flush=True)


def probe(lab, label, allowed=True):
    command = "wget -T 3 -qO- http://203.0.113.10/lab.txt | grep -qx LAB_OK"
    if not allowed:
        command = "! (" + command + ")"
    check(lab, label, command)


def capture(lab):
    (lab.state / "capture-start").write_text(
        str((lab.state / "wan-wire.pcap").stat().st_size)
    )


def leak_packets(lab):
    started = int((lab.state / "capture-start").read_text())
    data = (lab.state / "wan-wire.pcap").read_bytes()
    if len(data) < 24 or data[:4] not in {b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4"}:
        raise RuntimeError("Invalid or missing QEMU packet capture")
    endian = "<" if data[:4] == b"\xd4\xc3\xb2\xa1" else ">"
    offset = 24
    found = 0
    while offset + 16 <= len(data):
        _, _, length, _ = struct.unpack_from(endian + "IIII", data, offset)
        offset += 16
        packet = data[offset : offset + length]
        offset += length
        if len(packet) != length:
            raise RuntimeError(
                "Incomplete packet capture; retry after the writer flushes"
            )
        if offset <= started or len(packet) < 54:
            continue
        protocol = packet[12:14]
        destination = None
        if protocol == b"\x08\x00":
            destination = socket.inet_ntop(socket.AF_INET, packet[30:34])
        elif protocol == b"\x86\xdd":
            destination = socket.inet_ntop(socket.AF_INET6, packet[38:54])
        if destination in {"203.0.113.10", "fd77:77:3::10"}:
            found += 1
    return found


def no_leaks(lab, label):
    count = leak_packets(lab)
    with (lab.state / "evidence.jsonl").open("a") as evidence:
        evidence.write(
            json.dumps(
                {
                    "check": label,
                    "start_offset": int((lab.state / "capture-start").read_text()),
                    "end_offset": (lab.state / "wan-wire.pcap").stat().st_size,
                    "forbidden_packets": count,
                }
            )
            + "\n"
        )
    if count:
        raise RuntimeError(f"{label}: observed {count} forbidden WAN packets")
    print(f"PASS: {label} (host-side capture, 0 forbidden packets)", flush=True)


def verify(lab, phase):
    if phase == "wan":
        capture(lab)
        probe(lab, "WAN forwards real HTTP from LAN")
        check(
            lab,
            "WAN forwards IPv6 from LAN",
            "ping6 -c 2 -W 2 fd77:77:3::10 >/dev/null",
        )
        if leak_packets(lab) == 0:
            raise RuntimeError("WAN capture positive control saw no test traffic")
        print(
            "PASS: host-side capture positive control observed WAN traffic", flush=True
        )
    elif phase == "vless":
        check(
            lab,
            "VLESS activation",
            "/etc/init.d/maxvpn-sing-box start; sleep 2; /usr/bin/vpn-lan-vless-on",
            "router",
        )
        capture(lab)
        probe(lab, "VLESS carries real LAN HTTP to local peer")
        check(
            lab,
            "Explicit DIRECT remains reachable",
            "wget -T 3 -qO- http://203.0.113.20/lab.txt | grep -qx LAB_OK",
        )
        check(
            lab,
            "VLESS blocks IPv6 WAN fallback",
            "! ping6 -c 2 -W 1 fd77:77:3::10 >/dev/null",
        )
        no_leaks(lab, "No unmarked IPv4/IPv6 packets on WAN in VLESS mode")
    elif phase == "down":
        capture(lab)
        check(
            lab,
            "Stop tunnel while preserving selected mode",
            "/etc/init.d/maxvpn-vless-watchdog stop; /etc/init.d/maxvpn-sing-box stop; sleep 2; test $(cat /etc/maxvpn/runtime-mode) = vless",
            "router",
        )
        probe(lab, "Tunnel down blocks unmarked LAN HTTP", allowed=False)
        check(
            lab, "Tunnel down blocks IPv6", "! ping6 -c 2 -W 1 fd77:77:3::10 >/dev/null"
        )
        check(
            lab,
            "DIRECT survives tunnel loss",
            "wget -T 3 -qO- http://203.0.113.20/lab.txt | grep -qx LAB_OK",
        )
        no_leaks(lab, "No IPv4/IPv6 leakage with tunnel down")
        check(
            lab,
            "Watchdog enabled for autonomous recovery",
            "/etc/init.d/maxvpn-vless-watchdog start",
            "router",
        )
    elif phase == "recovered":
        probe(lab, "Watchdog restored real VLESS forwarding")
        check(
            lab,
            "Watchdog restored TUN policy",
            "ip route show table 100 | grep -q '^default dev maxvpn0'",
            "router",
        )
        no_leaks(
            lab, "No unmarked WAN packets during tunnel loss and watchdog recovery"
        )
    elif phase == "reload":
        capture(lab)
        check(lab, "Firewall reload", "/etc/init.d/firewall reload", "router")
        probe(lab, "VLESS forwarding survives firewall reload")
        check(
            lab,
            "DIRECT survives firewall reload",
            "wget -T 3 -qO- http://203.0.113.20/lab.txt | grep -qx LAB_OK",
        )
        check(
            lab,
            "IPv6 remains blocked after reload",
            "! ping6 -c 2 -W 1 fd77:77:3::10 >/dev/null",
        )
        no_leaks(lab, "No unmarked WAN traffic after reload")
    elif phase == "reboot":
        capture(lab)
        # Return before reboot tears down the console; recovery is checked separately.
        lab.command("router", "(sleep 1; reboot) >/dev/null 2>&1 &")
        print(
            "Router reboot requested; run recovered and vless phases after boot",
            flush=True,
        )
    elif phase == "boot-recovered":
        probe(lab, "VLESS forwarding restored after reboot")
        check(
            lab,
            "DIRECT restored after reboot",
            "wget -T 3 -qO- http://203.0.113.20/lab.txt | grep -qx LAB_OK",
        )
        check(
            lab,
            "IPv6 blocked after reboot",
            "! ping6 -c 2 -W 1 fd77:77:3::10 >/dev/null",
        )
        no_leaks(lab, "No unmarked LAN packets during reboot and recovery")
    elif phase == "probes-start":
        lab.command(
            "client",
            "(while :; do wget -T 1 -qO- http://203.0.113.10/lab.txt >/dev/null; ping6 -c 1 -W 1 fd77:77:3::10 >/dev/null; done) >/tmp/maxvpn-probes.log 2>&1 & echo $! >/tmp/maxvpn-probes.pid",
        )
        print("Started continuous IPv4 HTTP and IPv6 probes from LAN", flush=True)
    elif phase == "probes-stop":
        lab.command("client", "kill $(cat /tmp/maxvpn-probes.pid)")
    elif phase == "return-wan":
        check(lab, "Return to WAN", "/usr/bin/vpn-lan-off", "router")
        probe(lab, "WAN forwarding restored")
        check(lab, "WAN IPv6 restored", "ping6 -c 2 -W 2 fd77:77:3::10 >/dev/null")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True)
    parser.add_argument(
        "phase",
        choices=[
            "peer",
            "probes-start",
            "probes-stop",
            "boot-recovered",
            "setup",
            "wan",
            "vless",
            "down",
            "recovered",
            "reload",
            "reboot",
            "return-wan",
        ],
    )
    args = parser.parse_args()
    lab = Lab(args.state)
    if args.phase == "setup":
        setup(lab)
    elif args.phase == "peer":
        setup_peer(lab)
    else:
        verify(lab, args.phase)


if __name__ == "__main__":
    main()
