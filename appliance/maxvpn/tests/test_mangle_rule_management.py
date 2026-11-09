import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import pytest

os.environ.setdefault(
    "MAXVPN_APPLIANCE_ROOT",
    tempfile.mkdtemp(prefix="maxvpn-mangle-test-"),
)

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))
import server as appliance  # noqa: E402

CANONICAL = (
    "-A PREROUTING -i br-lan -m set "
    "--match-set MAXVPN_DIRECT dst -j MARK --set-xmark 0x64/0xff"
)

LEGACY = (
    "-A PREROUTING -i br-lan -m set "
    "--match-set MAXVPN_DIRECT dst -j MARK --set-xmark 0x64/0xffffffff"
)


def test_replaces_legacy_and_canonical_rules_but_preserves_foreign_rules(
    monkeypatch,
):
    listing = "\n".join(
        [
            LEGACY,
            CANONICAL,
            CANONICAL,
            (
                "-A PREROUTING -i br-guest -m set "
                "--match-set MAXVPN_DIRECT dst -j MARK --set-xmark 0x64/0xff"
            ),
            ("-A PREROUTING -i br-lan -m set --match-set MAXVPN_DIRECT dst -j ACCEPT"),
            (
                "-A PREROUTING -i br-lan -m set "
                "--match-set MAXVPN_DIRECT dst -j MARK --set-xmark 0x65/0xff"
            ),
            (
                "-A PREROUTING -i br-lan -m set "
                "--match-set OTHER_SET dst -j MARK --set-xmark 0x64/0xff"
            ),
        ]
    )

    calls = []

    def fake_run(command, check=True):
        calls.append(command)
        if command == ["iptables", "-t", "mangle", "-S", "PREROUTING"]:
            return SimpleNamespace(returncode=0, stdout=listing, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(appliance, "run", fake_run)

    appliance.ensure_canonical_mark_rule("MAXVPN_DIRECT")

    deletions = [
        command for command in calls if len(command) > 4 and command[3] == "-D"
    ]
    additions = [
        command for command in calls if len(command) > 4 and command[3] == "-A"
    ]

    assert len(deletions) == 3
    assert all("--match-set" in command for command in deletions)
    assert all("MAXVPN_DIRECT" in command for command in deletions)
    assert len(additions) == 1
    assert additions[0] == [
        "iptables",
        "-t",
        "mangle",
        "-A",
        "PREROUTING",
        "-i",
        appliance.LAN_IF,
        "-m",
        "set",
        "--match-set",
        "MAXVPN_DIRECT",
        "dst",
        "-j",
        "MARK",
        "--set-xmark",
        appliance.FWMARK,
    ]


def test_adds_canonical_rule_when_no_managed_rule_exists(monkeypatch):
    calls = []

    def fake_run(command, check=True):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(appliance, "run", fake_run)

    appliance.ensure_canonical_mark_rule("MAXVPN_DIRECT")

    assert len(calls) == 2
    assert calls[0] == [
        "iptables",
        "-t",
        "mangle",
        "-S",
        "PREROUTING",
    ]
    assert calls[1][3] == "-A"


@pytest.mark.parametrize(
    "foreign_rule",
    [
        (
            "-A PREROUTING -i br-guest -m set "
            "--match-set MAXVPN_DIRECT dst -j MARK --set-xmark 0x64/0xff"
        ),
        ("-A PREROUTING -i br-lan -m set --match-set MAXVPN_DIRECT dst -j ACCEPT"),
        (
            "-A PREROUTING -i br-lan -m set "
            "--match-set MAXVPN_DIRECT dst -j MARK --set-xmark 0x65/0xff"
        ),
    ],
)
def test_foreign_rules_are_not_deleted(monkeypatch, foreign_rule):
    calls = []

    def fake_run(command, check=True):
        calls.append(command)
        if command == ["iptables", "-t", "mangle", "-S", "PREROUTING"]:
            return SimpleNamespace(
                returncode=0,
                stdout=foreign_rule,
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(appliance, "run", fake_run)

    appliance.ensure_canonical_mark_rule("MAXVPN_DIRECT")

    deletions = [
        command for command in calls if len(command) > 4 and command[3] == "-D"
    ]

    assert deletions == []
    assert calls[-1][3] == "-A"
