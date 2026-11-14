"""Read-only DNS status for MaxVPN appliance."""

from __future__ import annotations

import ipaddress
import re
import subprocess
from pathlib import Path


def _command(args):
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        return result.returncode, result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return -1, ""


def _uci(name):
    code, output = _command(["uci", "-q", "get", name])
    return output if code == 0 else None


def _read_upstreams(path):
    addresses = []

    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()

        if len(parts) < 2 or parts[0] != "nameserver":
            continue

        try:
            address = str(ipaddress.ip_address(parts[1]))
        except ValueError:
            continue

        if address not in addresses:
            addresses.append(address)

    return addresses[:32]


def _route_for(address):
    family = "-6" if ":" in address else "-4"
    code, output = _command(["ip", family, "route", "get", address])

    if code != 0:
        return {
            "mode": "unknown",
            "interface": None,
            "table": None,
        }

    interface_match = re.search(r"\bdev\s+(\S+)", output)
    table_match = re.search(r"\btable\s+(\S+)", output)

    interface = interface_match.group(1) if interface_match else None
    table = table_match.group(1) if table_match else "main"

    if interface == "maxvpn0":
        mode = "vpn"
    elif interface == "eth1":
        mode = "wan"
    else:
        mode = "unknown"

    return {
        "mode": mode,
        "interface": interface,
        "table": table,
    }


def collect_dns_status():
    warnings = []

    process_code, processes = _command(["pidof", "dnsmasq"])

    resolv_file = _uci("dhcp.@dnsmasq[0].resolvfile")
    no_resolv = _uci("dhcp.@dnsmasq[0].noresolv")
    rebind = _uci("dhcp.@dnsmasq[0].rebind_protection")
    explicit_servers = _uci("dhcp.@dnsmasq[0].server")

    upstreams = []

    if no_resolv == "1":
        warnings.append("resolv_file_disabled")
    elif resolv_file:
        try:
            upstreams = _read_upstreams(resolv_file)
        except (OSError, UnicodeError):
            warnings.append("resolv_file_unavailable")
    else:
        warnings.append("resolv_file_not_configured")

    if explicit_servers:
        warnings.append("explicit_dns_servers_require_separate_parsing")

    return {
        "dnsmasq": {
            "running": process_code == 0 and bool(processes),
        },
        "configuration": {
            "resolv_file": resolv_file,
            "no_resolv": no_resolv == "1",
            "rebind_protection": (rebind == "1" if rebind in ("0", "1") else None),
        },
        "upstreams": [
            {
                "address": address,
                "source": "resolv-file",
                "route": _route_for(address),
                "active": None,
            }
            for address in upstreams
        ],
        "warnings": warnings,
    }
