import os
import sys
import tempfile
from pathlib import Path

os.environ["MAXVPN_APPLIANCE_ROOT"] = tempfile.mkdtemp(prefix="maxvpn-dns-status-test-")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import dns_status  # noqa: E402
import server as appliance  # noqa: E402


def test_dns_status_uses_configured_upstreams(tmp_path, monkeypatch):
    resolv = tmp_path / "resolv.conf"
    resolv.write_text(
        "nameserver 1.1.1.1\nnameserver 8.8.8.8\n",
        encoding="utf-8",
    )

    def command(args):
        if args == ["pidof", "dnsmasq"]:
            return 0, "7244 7249"

        if args[:3] == ["uci", "-q", "get"]:
            values = {
                "dhcp.@dnsmasq[0].resolvfile": str(resolv),
                "dhcp.@dnsmasq[0].rebind_protection": "0",
            }
            value = values.get(args[3])
            return (0, value) if value else (1, "")

        if args[:4] == ["ip", "-4", "route", "get"]:
            return (
                0,
                f"{args[4]} dev maxvpn0 table 100 src 172.19.0.1",
            )

        raise AssertionError(f"Unexpected command: {args}")

    monkeypatch.setattr(dns_status, "_command", command)

    result = dns_status.collect_dns_status()

    assert result["dnsmasq"]["running"] is True
    assert len(result["upstreams"]) == 2
    assert result["upstreams"][0]["address"] == "1.1.1.1"
    assert result["upstreams"][0]["route"]["mode"] == "vpn"
    assert result["upstreams"][0]["route"]["table"] == "100"
    assert result["upstreams"][0]["active"] is None
    assert result["configuration"]["rebind_protection"] is False


def test_missing_resolv_file_is_handled(monkeypatch):
    def command(args):
        if args == ["pidof", "dnsmasq"]:
            return 1, ""

        if args[:3] == ["uci", "-q", "get"]:
            if args[3].endswith(".resolvfile"):
                return 0, "/nonexistent/maxvpn-resolv"
            return 1, ""

        raise AssertionError(f"Unexpected command: {args}")

    monkeypatch.setattr(dns_status, "_command", command)

    result = dns_status.collect_dns_status()

    assert result["dnsmasq"]["running"] is False
    assert result["upstreams"] == []
    assert "resolv_file_unavailable" in result["warnings"]


def test_dns_status_api_route(monkeypatch):
    expected = {
        "dnsmasq": {"running": True},
        "upstreams": [],
    }
    calls = []

    monkeypatch.setattr(
        appliance,
        "collect_dns_status",
        lambda: expected,
    )

    handler = appliance.Handler.__new__(appliance.Handler)
    handler.path = "/api/appliance/v1/dns/status"
    handler.send_json = lambda code, payload: calls.append((code, payload))

    handler.do_GET()

    assert calls == [(200, expected)]
