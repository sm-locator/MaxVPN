import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import pytest

os.environ["MAXVPN_APPLIANCE_ROOT"] = tempfile.mkdtemp(
    prefix="maxvpn-wan-preflight-test-"
)
MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))
import server as appliance  # noqa: E402


def _prepare_database(tmp_path, monkeypatch):
    monkeypatch.setattr(appliance, "DB", tmp_path / "maxvpn.db")
    monkeypatch.setattr(appliance, "LOCK", tmp_path / "apply.lock")
    monkeypatch.setattr(
        appliance, "APPLIED_HASH_FILE", tmp_path / "applied_rules.sha256"
    )
    connection = appliance.db()
    connection.execute(
        """INSERT INTO rules
           (target_type, target, action, priority, address_family,
            enabled, created_at, comment)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("domain", "example.com", "direct", 10, "any", 1, 1, "WAN preflight test"),
    )
    connection.commit()
    connection.close()


def test_discover_network_clears_stale_gateway_when_default_route_is_missing(
    monkeypatch,
):
    monkeypatch.setattr(appliance, "WAN_GW", "192.0.2.1")
    monkeypatch.setattr(appliance, "uci_get", lambda path, default="": "eth1")

    def fake_run(command, check=True):
        assert command == ["ip", "route", "show", "default"]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(appliance, "run", fake_run)

    assert appliance.discover_network() == ("eth1", "")
    assert appliance.WAN_GW == ""


@pytest.mark.parametrize(
    "gateway",
    ["", "not-an-ip", "0.0.0.0", "224.0.0.1", "127.0.0.1"],
)
def test_apply_routing_rejects_unready_gateway_before_runtime_mutations(
    tmp_path, monkeypatch, gateway
):
    _prepare_database(tmp_path, monkeypatch)
    monkeypatch.setattr(appliance, "WAN_IF", "eth1")
    monkeypatch.setattr(appliance, "WAN_GW", gateway)
    monkeypatch.setattr(appliance, "discover_network", lambda: ("eth1", gateway))
    calls = []
    monkeypatch.setattr(
        appliance, "ensure_direct_path", lambda: calls.append("direct_path")
    )
    monkeypatch.setattr(
        appliance,
        "update_dnsmasq_domains",
        lambda domains: calls.append("dnsmasq_domains"),
    )
    monkeypatch.setattr(
        appliance, "rebuild_static_ipsets", lambda cidrs: calls.append("static_ipsets")
    )
    monkeypatch.setattr(
        appliance, "shell", lambda command, check=True: calls.append("shell")
    )
    monkeypatch.setattr(
        appliance, "set_applied_hash", lambda value: calls.append("applied_hash")
    )

    with pytest.raises(RuntimeError, match="WAN gateway"):
        appliance.apply_routing()

    assert calls == []
    assert not appliance.APPLIED_HASH_FILE.exists()


def test_apply_routing_proceeds_when_wan_gateway_is_valid(tmp_path, monkeypatch):
    _prepare_database(tmp_path, monkeypatch)
    monkeypatch.setattr(appliance, "ensure_dnsmasq_ipset_support", lambda: None)
    monkeypatch.setattr(appliance, "WAN_IF", "eth1")
    monkeypatch.setattr(appliance, "WAN_GW", "192.0.2.1")
    monkeypatch.setattr(appliance, "discover_network", lambda: ("eth1", "192.0.2.1"))
    calls = []
    monkeypatch.setattr(
        appliance, "ensure_direct_path", lambda: calls.append("direct_path")
    )
    monkeypatch.setattr(
        appliance,
        "update_dnsmasq_domains",
        lambda domains: calls.append(("domains", domains)),
    )
    monkeypatch.setattr(
        appliance, "rebuild_static_ipsets", lambda cidrs: calls.append(("cidrs", cidrs))
    )
    monkeypatch.setattr(
        appliance, "shell", lambda command, check=True: calls.append(("shell", command))
    )
    monkeypatch.setattr(
        appliance, "set_applied_hash", lambda value: calls.append(("hash", value))
    )
    monkeypatch.setattr(appliance, "routing_info", lambda: {"healthy": True})

    result = appliance.apply_routing()

    assert result == {"healthy": True}
    assert calls[0] == "direct_path"
    assert calls[1] == ("domains", ["example.com"])
    assert calls[2] == ("cidrs", [])
    assert calls[3] == ("shell", "/etc/init.d/dnsmasq reload")
    assert calls[4][0] == "hash"
