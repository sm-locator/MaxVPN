import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

os.environ["MAXVPN_APPLIANCE_ROOT"] = tempfile.mkdtemp(prefix="maxvpn-appliance-test-")

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))
import server as appliance  # noqa: E402


def _add_domain_rule(tmp_path, monkeypatch, *, enabled=True):
    monkeypatch.setattr(appliance, "DB", tmp_path / "maxvpn.db")
    connection = appliance.db()
    cursor = connection.execute(
        """INSERT INTO rules
           (target_type, target, action, priority, address_family,
            enabled, created_at, comment)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("domain", "example.com", "direct", 10, "any", int(enabled), 1, "test"),
    )
    rule_id = cursor.lastrowid
    connection.commit()
    connection.close()
    return int(rule_id)


def _runtime_state(config_hash):
    return {
        "config_hash": config_hash,
        "applied_config_hash": config_hash,
        "config_dirty": False,
        "direct_ipset": True,
        "static_ipset": True,
        "static_net_ipset": True,
        "mangle_direct": True,
        "mangle_static": True,
        "mangle_static_net": True,
        "mangle_direct_count": 1,
        "mangle_static_count": 1,
        "mangle_static_net_count": 1,
        "ip_rule": "100: from all fwmark 0x64/0xff lookup 200\n1000: from all iif br-lan lookup 100",
        "table_200": "default via 192.168.8.1 dev eth1",
        "wan_interface": "eth1",
        "wan_gateway": "192.168.8.1",
    }


def test_route_test_rule_returns_direct_when_ipset_and_marked_route_match(
    tmp_path, monkeypatch
):
    rule_id = _add_domain_rule(tmp_path, monkeypatch)
    current_hash = appliance.rule_config_hash()
    monkeypatch.setattr(appliance, "routing_info", lambda: _runtime_state(current_hash))

    def fake_run(command, check=True):
        if command[0] == "nslookup":
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "Server: 127.0.0.1\n"
                    "Address: 127.0.0.1#53\n"
                    "Name: example.com\n"
                    "Address 1: 93.184.216.34\n"
                ),
                stderr="",
            )
        if command[0] == "ipset" and command[1] == "list":
            return SimpleNamespace(
                returncode=0, stdout=f"Name: {command[2]}\n", stderr=""
            )
        if command[0] == "ipset" and command[1] == "test":
            member = command[2] == appliance.DIRECT_IPSET
            return SimpleNamespace(returncode=0 if member else 1, stdout="", stderr="")
        if command == ["ip", "-4", "route", "show", "table", "100"]:
            return SimpleNamespace(
                returncode=0,
                stdout="default dev maxvpn0 scope link\\n",
                stderr="",
            )
        if command[:4] == ["ip", "-4", "route", "get"]:
            if "mark" in command:
                output = (
                    "93.184.216.34 via 192.168.8.1 dev eth1 table 200 "
                    "src 192.168.8.1 mark 0x64"
                )
            else:
                output = "93.184.216.34 dev maxvpn0 table 100 src 172.19.0.1"
            return SimpleNamespace(returncode=0, stdout=output, stderr="")
        raise AssertionError(f"Unexpected command: {command!r}")

    monkeypatch.setattr(appliance, "run", fake_run)

    result = appliance.route_test_rule(rule_id)

    assert result is not None
    assert result["overall"] == "direct"
    assert result["resolution"] == {
        "ok": True,
        "addresses": ["93.184.216.34"],
    }
    assert result["destinations"][0]["decision"] == "direct"
    assert result["destinations"][0]["marked_route"]["ok"] is True
    assert result["destinations"][0]["unmarked_route"]["ok"] is True
    assert result["destinations"][0]["unmarked_route"]["dev"] == "maxvpn0"
    assert "table 100" in result["destinations"][0]["unmarked_route"]["raw"]
    assert result["summary"]["direct"] == 1


def test_route_test_unmarked_lookup_uses_longest_prefix_in_table_100(
    monkeypatch,
):
    def fake_run(command, check=True):
        assert command == ["ip", "-4", "route", "show", "table", "100"]
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "default dev maxvpn0 scope link\n"
                "93.184.216.0/24 via 46.48.56.1 dev eth1 proto static metric 5\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(appliance, "run", fake_run)

    result = appliance._route_test_lookup(
        "93.184.216.34", marked=False, lan_policy_present=True
    )

    assert result["ok"] is True
    assert result["dev"] == "eth1"
    assert result["via"] == "46.48.56.1"
    assert "table 100" in result["raw"]


def test_route_test_unmarked_lookup_requires_lan_policy(monkeypatch):
    def unexpected_run(command, check=True):
        raise AssertionError(f"Unexpected command: {command!r}")

    monkeypatch.setattr(appliance, "run", unexpected_run)

    result = appliance._route_test_lookup(
        "93.184.216.34", marked=False, lan_policy_present=False
    )

    assert result["ok"] is False
    assert result["returncode"] != 0
    assert "iif br-lan lookup 100" in result["raw"]


def test_route_test_rule_returns_none_for_missing_rule(tmp_path, monkeypatch):
    monkeypatch.setattr(appliance, "DB", tmp_path / "maxvpn.db")
    assert appliance.route_test_rule(99999) is None


def test_route_test_rule_reports_disabled_rule(tmp_path, monkeypatch):
    rule_id = _add_domain_rule(tmp_path, monkeypatch, enabled=False)
    current_hash = appliance.rule_config_hash()
    monkeypatch.setattr(appliance, "routing_info", lambda: _runtime_state(current_hash))

    def fake_run(command, check=True):
        if command[0] == "nslookup":
            return SimpleNamespace(
                returncode=0,
                stdout="Name: example.com\nAddress 1: 93.184.216.34\n",
                stderr="",
            )
        if command[0] == "ipset" and command[1] == "list":
            return SimpleNamespace(returncode=0, stdout="Name: test\n", stderr="")
        if command[0] == "ipset" and command[1] == "test":
            return SimpleNamespace(returncode=1, stdout="", stderr="not a member")
        if command == ["ip", "-4", "route", "show", "table", "100"]:
            return SimpleNamespace(
                returncode=0,
                stdout="default dev maxvpn0 scope link\\n",
                stderr="",
            )
        if command[:4] == ["ip", "-4", "route", "get"]:
            return SimpleNamespace(
                returncode=0,
                stdout="93.184.216.34 dev maxvpn0 table 100",
                stderr="",
            )
        raise AssertionError(f"Unexpected command: {command!r}")

    monkeypatch.setattr(appliance, "run", fake_run)

    result = appliance.route_test_rule(rule_id)

    assert result is not None
    assert result["overall"] == "disabled"
    assert result["destinations"][0]["decision"] == "disabled"
    assert result["summary"]["disabled"] == 1
