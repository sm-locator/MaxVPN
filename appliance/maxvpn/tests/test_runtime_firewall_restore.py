import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import pytest

os.environ["MAXVPN_APPLIANCE_ROOT"] = tempfile.mkdtemp(
    prefix="maxvpn-runtime-firewall-test-"
)

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))
import server as appliance  # noqa: E402

IPV4_CHAIN = ("iptables", "-S", "MAXVPN_LAN_FORWARD")
IPV4_FORWARD = ("iptables", "-S", "forwarding_rule")
IPV6_CHAIN = ("ip6tables", "-S", "MAXVPN_LAN6_FORWARD")
IPV6_FORWARD = ("ip6tables", "-S", "forwarding_rule")
NAT_CHAIN = ("iptables", "-t", "nat", "-S", "MAXVPN_DIRECT_NAT")
POSTROUTING = ("iptables", "-t", "nat", "-S", "POSTROUTING")

IPV4_JUMP = "-A forwarding_rule -j MAXVPN_LAN_FORWARD"
IPV6_JUMP = "-A forwarding_rule -j MAXVPN_LAN6_FORWARD"
NAT_JUMP = "-A POSTROUTING -j MAXVPN_DIRECT_NAT"

NAT_RULES = [
    "-A MAXVPN_DIRECT_NAT -o eth1 -m mark --mark 0x64/0xff -j MASQUERADE",
    "-A MAXVPN_DIRECT_NAT -j RETURN",
]


def _rules_for_mode(mode):
    if mode == "wan":
        ipv4 = [
            "-A MAXVPN_LAN_FORWARD -i br-lan -o eth1 -j ACCEPT",
            "-A MAXVPN_LAN_FORWARD -j RETURN",
        ]
        ipv6 = [
            "-A MAXVPN_LAN6_FORWARD -i br-lan -o eth1 -j ACCEPT",
            "-A MAXVPN_LAN6_FORWARD -j RETURN",
        ]
    elif mode == "vless":
        ipv4 = [
            "-A MAXVPN_LAN_FORWARD -i br-lan -o maxvpn0 -j ACCEPT",
            "-A MAXVPN_LAN_FORWARD -i br-lan -o eth1 -m mark --mark 0x64/0xff -j ACCEPT",
            "-A MAXVPN_LAN_FORWARD -i br-lan -o eth1 -j DROP",
            "-A MAXVPN_LAN_FORWARD -j RETURN",
        ]
        ipv6 = [
            "-A MAXVPN_LAN6_FORWARD -i br-lan -j DROP",
            "-A MAXVPN_LAN6_FORWARD -j RETURN",
        ]
    else:
        ipv4 = [
            "-A MAXVPN_LAN_FORWARD -i br-lan -o WireGuard -j ACCEPT",
            "-A MAXVPN_LAN_FORWARD -i br-lan -o eth1 -m mark --mark 0x64/0xff -j ACCEPT",
            "-A MAXVPN_LAN_FORWARD -i br-lan -o eth1 -j DROP",
            "-A MAXVPN_LAN_FORWARD -j RETURN",
        ]
        ipv6 = [
            "-A MAXVPN_LAN6_FORWARD -i br-lan -o WireGuard -j ACCEPT",
            "-A MAXVPN_LAN6_FORWARD -i br-lan -o eth1 -j DROP",
            "-A MAXVPN_LAN6_FORWARD -j RETURN",
        ]

    return {
        IPV4_CHAIN: ipv4,
        IPV4_FORWARD: [IPV4_JUMP],
        IPV6_CHAIN: ipv6,
        IPV6_FORWARD: [IPV6_JUMP],
        NAT_CHAIN: NAT_RULES.copy(),
        POSTROUTING: [NAT_JUMP],
    }


@pytest.fixture
def firewall_harness(tmp_path, monkeypatch):
    mode_file = tmp_path / "runtime-mode"
    monkeypatch.setattr(appliance, "RUNTIME_MODE_FILE", mode_file)

    outputs = {}

    def install(mode):
        mode_file.write_text(mode, encoding="utf-8")
        outputs.clear()
        outputs.update(
            {
                command: (0, lines.copy(), "")
                for command, lines in _rules_for_mode(mode).items()
            }
        )

    def fake_run(command, check=True):
        key = tuple(command)
        if key not in outputs:
            raise AssertionError(f"Unexpected command: {command!r}")

        returncode, lines, stderr = outputs[key]
        stdout = "\n".join(lines)
        if stdout:
            stdout += "\n"

        return SimpleNamespace(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    monkeypatch.setattr(appliance, "run", fake_run)
    return mode_file, outputs, install


@pytest.mark.parametrize("mode", ["vpn", "vless", "wan"])
def test_verify_runtime_firewall_accepts_renderer_rules_for_each_mode(
    firewall_harness, mode
):
    _, _, install = firewall_harness
    install(mode)

    result = appliance.verify_runtime_firewall()

    assert result == {
        "mode": mode,
        "ipv4": True,
        "ipv6": True,
        "nat": True,
        "nat_jump_count": 1,
    }


def test_verify_runtime_firewall_defaults_to_vpn_when_mode_file_is_missing(
    firewall_harness,
):
    mode_file, _, install = firewall_harness
    install("vpn")
    mode_file.unlink()

    result = appliance.verify_runtime_firewall()

    assert result["mode"] == "vpn"


def test_verify_runtime_firewall_defaults_to_vpn_for_unknown_mode(
    firewall_harness,
):
    mode_file, _, install = firewall_harness
    install("vpn")
    mode_file.write_text("unexpected-mode", encoding="utf-8")

    result = appliance.verify_runtime_firewall()

    assert result["mode"] == "vpn"


@pytest.mark.parametrize(
    ("command", "duplicate_rule", "message"),
    [
        (IPV4_FORWARD, IPV4_JUMP, "IPv4 firewall chain"),
        (IPV6_FORWARD, IPV6_JUMP, "IPv6 firewall chain"),
        (POSTROUTING, NAT_JUMP, "DIRECT NAT chain"),
    ],
)
def test_verify_runtime_firewall_rejects_duplicate_jumps(
    firewall_harness, command, duplicate_rule, message
):
    _, outputs, install = firewall_harness
    install("vless")

    returncode, lines, stderr = outputs[command]
    outputs[command] = (returncode, lines + [duplicate_rule], stderr)

    with pytest.raises(RuntimeError, match=message):
        appliance.verify_runtime_firewall()


@pytest.mark.parametrize(
    ("command", "jump", "message"),
    [
        (IPV4_FORWARD, IPV4_JUMP, "IPv4 firewall chain"),
        (IPV6_FORWARD, IPV6_JUMP, "IPv6 firewall chain"),
        (POSTROUTING, NAT_JUMP, "DIRECT NAT chain"),
    ],
)
def test_verify_runtime_firewall_rejects_jump_not_in_first_position(
    firewall_harness, command, jump, message
):
    _, outputs, install = firewall_harness
    install("vless")

    outputs[command] = (
        0,
        (
            ["-A forwarding_rule -j ACCEPT", jump]
            if command != POSTROUTING
            else ["-A POSTROUTING -j ACCEPT", jump]
        ),
        "",
    )

    with pytest.raises(RuntimeError, match=message):
        appliance.verify_runtime_firewall()


def test_verify_runtime_firewall_rejects_missing_chain(firewall_harness):
    _, outputs, install = firewall_harness
    install("vless")
    outputs[IPV4_CHAIN] = (1, [], "No chain/target/match by that name")

    with pytest.raises(RuntimeError, match="firewall inspection failed"):
        appliance.verify_runtime_firewall()


def test_restore_runtime_firewall_executes_script_and_verifies_state(
    tmp_path, monkeypatch
):
    script = tmp_path / "firewall.user"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)

    monkeypatch.setattr(appliance, "FIREWALL_USER_SCRIPT", script)

    calls = []

    def fake_run(command, check=True):
        calls.append((command, check))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    expected = {"mode": "vless", "nat_jump_count": 1}
    monkeypatch.setattr(appliance, "run", fake_run)
    monkeypatch.setattr(appliance, "verify_runtime_firewall", lambda: expected)

    assert appliance.restore_runtime_firewall() == expected
    assert calls == [(["/bin/sh", "-e", str(script)], False)]


def test_restore_runtime_firewall_rejects_script_execution_failure(
    tmp_path, monkeypatch
):
    script = tmp_path / "firewall.user"
    script.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    script.chmod(0o755)

    monkeypatch.setattr(appliance, "FIREWALL_USER_SCRIPT", script)
    monkeypatch.setattr(
        appliance,
        "run",
        lambda command, check=True: SimpleNamespace(
            returncode=1, stdout="", stderr="simulated iptables failure"
        ),
    )

    with pytest.raises(RuntimeError, match="simulated iptables failure"):
        appliance.restore_runtime_firewall()


def test_restore_runtime_firewall_rejects_missing_script(tmp_path, monkeypatch):
    monkeypatch.setattr(
        appliance, "FIREWALL_USER_SCRIPT", tmp_path / "missing-firewall.user"
    )

    with pytest.raises(RuntimeError, match="firewall script is missing"):
        appliance.restore_runtime_firewall()
