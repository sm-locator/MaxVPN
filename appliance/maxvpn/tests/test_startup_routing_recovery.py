import logging
import os
from pathlib import Path
import sys
import tempfile

os.environ["MAXVPN_APPLIANCE_ROOT"] = tempfile.mkdtemp(prefix="maxvpn-appliance-test-")

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))
import server as appliance  # noqa: E402


def _add_domain_rule(tmp_path, monkeypatch):
    monkeypatch.setattr(appliance, "DB", tmp_path / "maxvpn.db")
    monkeypatch.setattr(
        appliance, "APPLIED_HASH_FILE", tmp_path / "applied_rules.sha256"
    )
    connection = appliance.db()
    connection.execute(
        """INSERT INTO rules
           (target_type, target, action, priority, address_family,
            enabled, created_at, comment)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("domain", "example.com", "direct", 10, "any", 1, 1, "startup test"),
    )
    connection.commit()
    connection.close()


def test_startup_skips_routing_rebuild_when_hash_already_applied(
    tmp_path, monkeypatch, caplog
):
    _add_domain_rule(tmp_path, monkeypatch)
    current_hash = appliance.rule_config_hash()
    appliance.set_applied_hash(current_hash)

    def unexpected_apply():
        raise AssertionError("apply_routing must not run for an unchanged config")

    monkeypatch.setattr(appliance, "apply_routing", unexpected_apply)

    with caplog.at_level(logging.INFO, logger="maxvpn-appliance"):
        assert appliance.ensure_applied_baseline() is False

    assert appliance.get_applied_hash() == current_hash
    assert "startup restore skipped" in caplog.text


def test_forced_restore_rebuilds_routing_when_hash_already_matches(
    tmp_path, monkeypatch
):
    _add_domain_rule(tmp_path, monkeypatch)
    current_hash = appliance.rule_config_hash()
    appliance.set_applied_hash(current_hash)
    calls = []

    def successful_apply():
        calls.append("apply")
        appliance.set_applied_hash(appliance.rule_config_hash())

    monkeypatch.setattr(appliance, "apply_routing", successful_apply)

    assert appliance.ensure_applied_baseline(force=True) is True
    assert calls == ["apply"]
    assert appliance.get_applied_hash() == current_hash


def test_startup_rebuilds_routing_when_hash_differs(tmp_path, monkeypatch, caplog):
    _add_domain_rule(tmp_path, monkeypatch)
    current_hash = appliance.rule_config_hash()
    appliance.set_applied_hash("f" * 64)
    calls = []

    def successful_apply():
        calls.append("apply")
        appliance.set_applied_hash(appliance.rule_config_hash())

    monkeypatch.setattr(appliance, "apply_routing", successful_apply)

    with caplog.at_level(logging.INFO, logger="maxvpn-appliance"):
        assert appliance.ensure_applied_baseline() is True

    assert calls == ["apply"]
    assert appliance.get_applied_hash() == current_hash
    assert "startup restore completed" in caplog.text


def test_startup_apply_error_keeps_previous_applied_hash(tmp_path, monkeypatch, caplog):
    _add_domain_rule(tmp_path, monkeypatch)
    previous_hash = "a" * 64
    appliance.set_applied_hash(previous_hash)

    def failing_apply():
        raise RuntimeError("simulated routing failure")

    monkeypatch.setattr(appliance, "apply_routing", failing_apply)

    with caplog.at_level(logging.ERROR, logger="maxvpn-appliance"):
        assert appliance.ensure_applied_baseline() is False

    assert appliance.get_applied_hash() == previous_hash
    assert "startup restore failed" in caplog.text
    assert "simulated routing failure" in caplog.text


def test_startup_recovery_does_not_access_vless_control(tmp_path, monkeypatch):
    _add_domain_rule(tmp_path, monkeypatch)
    appliance.set_applied_hash("b" * 64)

    class VlessAccessForbidden:
        def __getattr__(self, name):
            raise AssertionError(
                "startup routing recovery accessed VLESS_CONTROL." + name
            )

    monkeypatch.setattr(appliance, "VLESS_CONTROL", VlessAccessForbidden())

    def successful_apply():
        appliance.set_applied_hash(appliance.rule_config_hash())

    monkeypatch.setattr(appliance, "apply_routing", successful_apply)

    assert appliance.ensure_applied_baseline() is True
