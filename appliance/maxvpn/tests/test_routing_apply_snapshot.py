import os
import sys
import tempfile
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import Mock

import pytest

os.environ["MAXVPN_APPLIANCE_ROOT"] = tempfile.mkdtemp(
    prefix="maxvpn-routing-snapshot-test-"
)

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))
import server as appliance  # noqa: E402


@pytest.fixture
def routing_state(tmp_path, monkeypatch):
    monkeypatch.setattr(appliance, "DB", tmp_path / "maxvpn.db")
    monkeypatch.setattr(appliance, "LOCK", tmp_path / "apply.lock")
    monkeypatch.setattr(
        appliance, "APPLIED_HASH_FILE", tmp_path / "applied_rules.sha256"
    )
    connection = appliance.db()
    connection.executemany(
        """INSERT INTO rules
           (target_type, target, action, priority, address_family,
            enabled, created_at, comment)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            ("domain", "before.example", "direct", 10, "any", 1, 1, "enabled"),
            ("cidr", "192.0.2.0/24", "direct", 20, "ipv4", 0, 1, "disabled"),
        ],
    )
    connection.commit()
    connection.close()

    monkeypatch.setattr(appliance, "discover_network", lambda: None)
    monkeypatch.setattr(appliance, "ensure_dnsmasq_ipset_support", lambda: None)
    monkeypatch.setattr(appliance, "WAN_IF", "eth1")
    monkeypatch.setattr(appliance, "WAN_GW", "192.0.2.1")
    monkeypatch.setattr(appliance, "ensure_direct_path", lambda: None)
    monkeypatch.setattr(appliance, "shell", lambda command: None)
    monkeypatch.setattr(appliance, "routing_info", lambda: {})
    return appliance.rule_config_hash()


def test_missing_dnsmasq_ipset_aborts_before_runtime_changes(
    routing_state, monkeypatch
):
    def unsupported():
        raise RuntimeError("dnsmasq_ipset_support_required")

    monkeypatch.setattr(appliance, "ensure_dnsmasq_ipset_support", unsupported)
    changed = Mock()
    monkeypatch.setattr(appliance, "ensure_direct_path", changed)
    with pytest.raises(RuntimeError, match="dnsmasq_ipset_support_required"):
        appliance.apply_routing()
    changed.assert_not_called()
    assert appliance.get_applied_hash() == ""


@pytest.mark.parametrize(
    "features,code,supported",
    [
        ("Compile time options: no-ipset", 0, False),
        ("Compile time options: IPv6 ipset conntrack", 0, True),
        ("", 1, False),
    ],
)
def test_dnsmasq_feature_check(monkeypatch, features, code, supported):
    monkeypatch.setattr(
        appliance,
        "run",
        lambda *args, **kwargs: CompletedProcess([], code, stdout=features),
    )
    if supported:
        appliance.ensure_dnsmasq_ipset_support()
    else:
        with pytest.raises(RuntimeError, match="dnsmasq_ipset_support_required"):
            appliance.ensure_dnsmasq_ipset_support()


def test_unchanged_snapshot_includes_disabled_rules_in_applied_hash(
    routing_state, monkeypatch
):
    domains, cidrs = [], []
    monkeypatch.setattr(appliance, "update_dnsmasq_domains", domains.extend)
    monkeypatch.setattr(appliance, "rebuild_static_ipsets", cidrs.extend)

    appliance.apply_routing()

    assert domains == ["before.example"]
    assert cidrs == []
    assert appliance.get_applied_hash() == routing_state
    assert appliance.get_applied_hash() == appliance.rule_config_hash()


@pytest.mark.parametrize(
    "edit",
    [
        "UPDATE rules SET target='after.example' WHERE target_type='domain'",
        "UPDATE rules SET enabled=0 WHERE target_type='domain'",
        "UPDATE rules SET enabled=1 WHERE target_type='cidr'",
        "DELETE FROM rules WHERE target_type='domain'",
        """INSERT INTO rules
           (target_type, target, action, priority, address_family,
            enabled, created_at, comment)
           VALUES ('domain','added.example','direct',30,'any',1,1,'added')""",
    ],
)
def test_edit_during_apply_stays_pending_until_next_recovery(
    routing_state, monkeypatch, edit
):
    applied_domains, applied_cidrs = [], []

    def apply_domains_and_edit(domains):
        applied_domains.append(list(domains))
        connection = appliance.db()
        connection.execute(edit)
        connection.commit()
        connection.close()

    monkeypatch.setattr(appliance, "update_dnsmasq_domains", apply_domains_and_edit)
    monkeypatch.setattr(
        appliance,
        "rebuild_static_ipsets",
        lambda cidrs: applied_cidrs.append(list(cidrs)),
    )

    appliance.apply_routing()

    assert applied_domains == [["before.example"]]
    assert applied_cidrs == [[]]
    assert appliance.get_applied_hash() == routing_state
    assert appliance.get_applied_hash() != appliance.rule_config_hash()

    current_rows = [row for row in appliance.list_rules() if row["enabled"]]
    expected_domains = [
        r["target"] for r in current_rows if r["target_type"] == "domain"
    ]
    expected_cidrs = [r["target"] for r in current_rows if r["target_type"] == "cidr"]
    monkeypatch.setattr(
        appliance,
        "update_dnsmasq_domains",
        lambda domains: applied_domains.append(list(domains)),
    )

    assert appliance.ensure_applied_baseline() is True
    assert applied_domains[-1] == expected_domains
    assert applied_cidrs[-1] == expected_cidrs
    assert appliance.get_applied_hash() == appliance.rule_config_hash()
