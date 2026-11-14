from unittest.mock import Mock

from backend.models.amneziawg_runtime_health import (
    AmneziaWGRuntimeHealth,
)
from backend.models.amneziawg_runtime_snapshot import (
    AmneziaWGRuntimeSnapshot,
)
from backend.services.amneziawg_runtime_manager import (
    AmneziaWGRuntimeManager,
)
from backend.services.amneziawg_runtime_applier import (
    AmneziaWGRuntimeApplyResult,
    AmneziaWGRuntimePlan,
)


def make_config():
    return Mock()


def make_plan() -> AmneziaWGRuntimePlan:
    return AmneziaWGRuntimePlan(
        interface="WireGuard",
        runtime_path="/tmp/runtime.conf",
        runtime_config="config",
        upload_command=("upload",),
        sync_command=("sync",),
    )


def make_apply_result(
    *,
    applied: bool,
    reason: str | None = None,
) -> AmneziaWGRuntimeApplyResult:
    return AmneziaWGRuntimeApplyResult(
        plan=make_plan(),
        upload_returncode=0,
        sync_returncode=0 if applied else 1,
        uploaded=applied,
        applied=applied,
        reason=reason,
    )


def make_health(
    *,
    healthy: bool,
    reason: str | None = None,
) -> AmneziaWGRuntimeHealth:
    return AmneziaWGRuntimeHealth(
        interface_exists=True,
        interface_up=True,
        expected_peer_found=True,
        expected_endpoint=True,
        listen_port=47182,
        latest_handshake=None,
        rx_bytes=1,
        tx_bytes=1,
        endpoint_route_ok=True,
        healthy=healthy,
        reason=reason,
        checked_at=Mock(),
    )


def make_manager():
    applier = Mock()
    snapshot = Mock()
    health_checker = Mock()
    lifecycle = Mock()

    lifecycle.exists.return_value = True

    manager = AmneziaWGRuntimeManager(
        applier=applier,
        snapshot=snapshot,
        health_checker=health_checker,
        lifecycle=lifecycle,
        wait_seconds=0,
    )

    return (
        manager,
        applier,
        snapshot,
        health_checker,
        lifecycle,
    )


def test_apply_succeeds_when_new_runtime_is_healthy() -> None:
    manager, applier, snapshot, health, lifecycle = make_manager()

    previous = AmneziaWGRuntimeSnapshot(
        interface="WireGuard",
        config_text="[Interface]\nPrivateKey = old\n",
    )

    snapshot.capture.return_value = previous
    applier.apply.return_value = make_apply_result(applied=True)
    health.check.return_value = make_health(healthy=True)

    result = manager.apply(make_config())

    assert result.applied is True
    assert result.verified is True
    assert result.rolled_back is False
    assert result.rollback_verified is False
    assert result.health_failed is False
    assert result.reason is None

    snapshot.capture.assert_called_once_with("WireGuard")
    snapshot.restore.assert_not_called()


def test_apply_failure_does_not_rollback_because_runtime_was_not_changed() -> None:
    manager, applier, snapshot, health, lifecycle = make_manager()

    snapshot.capture.return_value = Mock()
    applier.apply.return_value = make_apply_result(
        applied=False,
        reason="awg_syncconf_failed",
    )

    result = manager.apply(make_config())

    assert result.applied is False
    assert result.verified is False
    assert result.rolled_back is False
    assert result.rollback_verified is False
    assert result.health_failed is False
    assert result.reason == "awg_syncconf_failed"

    health.check.assert_not_called()
    snapshot.restore.assert_not_called()


def test_capture_failure_prevents_apply() -> None:
    manager, applier, snapshot, health, lifecycle = make_manager()

    snapshot.capture.side_effect = RuntimeError("ssh unavailable")

    result = manager.apply(make_config())

    assert result.applied is False
    assert result.verified is False
    assert result.rolled_back is False
    assert result.rollback_verified is False
    assert result.reason == "snapshot_capture_failed: ssh unavailable"

    applier.apply.assert_not_called()
    health.check.assert_not_called()


def test_unhealthy_new_runtime_is_rolled_back_and_verified() -> None:
    manager, applier, snapshot, health, lifecycle = make_manager()

    previous = AmneziaWGRuntimeSnapshot(
        interface="WireGuard",
        config_text="[Interface]\nPrivateKey = old\n",
    )

    snapshot.capture.return_value = previous
    applier.apply.return_value = make_apply_result(applied=True)
    health.check.side_effect = [
        make_health(
            healthy=False,
            reason="stale_handshake",
        ),
        make_health(healthy=True),
    ]

    result = manager.apply(make_config())

    assert result.applied is True
    assert result.verified is False
    assert result.rolled_back is True
    assert result.rollback_verified is True
    assert result.health_failed is True
    assert result.reason == ("awg_health_verification_failed: stale_handshake")

    snapshot.restore.assert_called_once_with(previous)


def test_rollback_failure_is_reported() -> None:
    manager, applier, snapshot, health, lifecycle = make_manager()

    previous = Mock()

    snapshot.capture.return_value = previous
    applier.apply.return_value = make_apply_result(applied=True)
    health.check.return_value = make_health(
        healthy=False,
        reason="stale_handshake",
    )
    snapshot.restore.side_effect = RuntimeError("restore failed")

    result = manager.apply(make_config())

    assert result.applied is True
    assert result.verified is False
    assert result.rolled_back is True
    assert result.rollback_verified is False
    assert result.health_failed is True
    assert result.reason == (
        "awg_health_verification_failed: stale_handshake; "
        "rollback_failed: restore failed"
    )


def test_rollback_health_failure_is_reported() -> None:
    manager, applier, snapshot, health, lifecycle = make_manager()

    previous = Mock()

    snapshot.capture.return_value = previous
    applier.apply.return_value = make_apply_result(applied=True)
    health.check.side_effect = [
        make_health(
            healthy=False,
            reason="stale_handshake",
        ),
        make_health(
            healthy=False,
            reason="interface_down",
        ),
    ]

    result = manager.apply(make_config())

    assert result.applied is True
    assert result.verified is False
    assert result.rolled_back is True
    assert result.rollback_verified is False
    assert result.health_failed is True
    assert result.reason == (
        "awg_health_verification_failed: stale_handshake; "
        "rollback_health_failed: interface_down"
    )

    snapshot.restore.assert_called_once_with(previous)


def test_apply_brings_up_missing_interface() -> None:
    manager, applier, snapshot, health, lifecycle = make_manager()

    previous = AmneziaWGRuntimeSnapshot(
        interface="WireGuard",
        config_text="[Interface]\\nPrivateKey = old\\n",
    )

    lifecycle.exists.return_value = False
    snapshot.capture.return_value = previous
    applier.apply.return_value = make_apply_result(applied=True)
    health.check.return_value = make_health(healthy=True)

    result = manager.apply(make_config())

    assert result.applied is True
    assert result.verified is True
    assert result.rolled_back is False
    assert result.health_failed is False
    assert result.reason is None

    lifecycle.exists.assert_called_once_with("WireGuard")
    lifecycle.bring_up.assert_called_once_with("WireGuard")
    lifecycle.bring_down.assert_not_called()

    snapshot.capture.assert_called_once_with("WireGuard")
    applier.apply.assert_called_once()
    snapshot.restore.assert_not_called()


def test_missing_interface_is_brought_down_when_snapshot_capture_fails() -> None:
    manager, applier, snapshot, health, lifecycle = make_manager()

    lifecycle.exists.return_value = False
    snapshot.capture.side_effect = RuntimeError("ssh unavailable")

    result = manager.apply(make_config())

    assert result.applied is False
    assert result.verified is False
    assert result.rolled_back is False
    assert result.health_failed is False
    assert result.reason == "snapshot_capture_failed: ssh unavailable"

    lifecycle.exists.assert_called_once_with("WireGuard")
    lifecycle.bring_up.assert_called_once_with("WireGuard")
    lifecycle.bring_down.assert_called_once_with("WireGuard")

    applier.apply.assert_not_called()
    health.check.assert_not_called()


def test_missing_interface_is_brought_down_when_apply_fails() -> None:
    manager, applier, snapshot, health, lifecycle = make_manager()

    lifecycle.exists.return_value = False
    snapshot.capture.return_value = Mock()
    applier.apply.return_value = make_apply_result(
        applied=False,
        reason="awg_syncconf_failed",
    )

    result = manager.apply(make_config())

    assert result.applied is False
    assert result.verified is False
    assert result.rolled_back is False
    assert result.health_failed is False
    assert result.reason == "awg_syncconf_failed"

    lifecycle.bring_up.assert_called_once_with("WireGuard")
    lifecycle.bring_down.assert_called_once_with("WireGuard")

    health.check.assert_not_called()
    snapshot.restore.assert_not_called()


def test_waits_before_initial_health_check() -> None:
    applier = Mock()
    snapshot = Mock()
    health = Mock()
    sleeper = Mock()

    snapshot.capture.return_value = Mock()
    applier.apply.return_value = make_apply_result(applied=True)
    health.check.return_value = make_health(healthy=True)

    lifecycle = Mock()
    lifecycle.exists.return_value = True

    manager = AmneziaWGRuntimeManager(
        applier=applier,
        snapshot=snapshot,
        health_checker=health,
        lifecycle=lifecycle,
        wait_seconds=15,
        sleeper=sleeper,
    )

    result = manager.apply(make_config())

    assert result.verified is True
    sleeper.assert_called_once_with(15)
