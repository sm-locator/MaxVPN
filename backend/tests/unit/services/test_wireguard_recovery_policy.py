import pytest
from backend.models.wireguard_health import WireGuardHealthStatus
from backend.models.wireguard_recovery import (
    WireGuardRecoveryAction,
)
from backend.services.wireguard_recovery_policy import (
    WireGuardRecoveryPolicy,
)


def test_healthy_state_requires_no_recovery() -> None:
    policy = WireGuardRecoveryPolicy()

    plan = policy.plan(
        status=WireGuardHealthStatus.HEALTHY,
        recovery_required=False,
        attempt=1,
        reason=None,
    )

    assert plan.action is WireGuardRecoveryAction.NONE
    assert plan.attempt == 1
    assert plan.max_attempts == 3
    assert plan.backoff_seconds == 0
    assert plan.reason is None


def test_degraded_state_does_not_trigger_recovery() -> None:
    policy = WireGuardRecoveryPolicy()

    plan = policy.plan(
        status=WireGuardHealthStatus.DEGRADED,
        recovery_required=False,
        attempt=1,
        reason="stale_handshake",
    )

    assert plan.action is WireGuardRecoveryAction.NONE
    assert plan.backoff_seconds == 0
    assert plan.reason == "stale_handshake"


def test_first_failed_attempt_restarts_interface() -> None:
    policy = WireGuardRecoveryPolicy()

    plan = policy.plan(
        status=WireGuardHealthStatus.FAILED,
        recovery_required=True,
        attempt=1,
        reason="handshake_timeout",
    )

    assert plan.action is WireGuardRecoveryAction.RESTART_INTERFACE
    assert plan.attempt == 1
    assert plan.backoff_seconds == 5
    assert plan.max_attempts == 3
    assert plan.reason == "handshake_timeout"


def test_second_failed_attempt_uses_second_backoff() -> None:
    policy = WireGuardRecoveryPolicy()

    plan = policy.plan(
        status=WireGuardHealthStatus.FAILED,
        recovery_required=True,
        attempt=2,
        reason="handshake_timeout",
    )

    assert plan.action is WireGuardRecoveryAction.RESTART_INTERFACE
    assert plan.backoff_seconds == 15


def test_third_failed_attempt_uses_third_backoff() -> None:
    policy = WireGuardRecoveryPolicy()

    plan = policy.plan(
        status=WireGuardHealthStatus.FAILED,
        recovery_required=True,
        attempt=3,
        reason="handshake_timeout",
    )

    assert plan.action is WireGuardRecoveryAction.RESTART_INTERFACE
    assert plan.backoff_seconds == 30


def test_attempt_above_limit_disables_recovery() -> None:
    policy = WireGuardRecoveryPolicy()

    plan = policy.plan(
        status=WireGuardHealthStatus.FAILED,
        recovery_required=True,
        attempt=4,
        reason="handshake_timeout",
    )

    assert plan.action is WireGuardRecoveryAction.NONE
    assert plan.backoff_seconds == 0
    assert plan.reason == "max_attempts_exceeded"


def test_recovery_requires_failed_state() -> None:
    policy = WireGuardRecoveryPolicy()

    plan = policy.plan(
        status=WireGuardHealthStatus.DEGRADED,
        recovery_required=True,
        attempt=1,
        reason="stale_handshake",
    )

    assert plan.action is WireGuardRecoveryAction.NONE
    assert plan.reason == "recovery_requires_failed_state"


def test_zero_attempt_is_rejected() -> None:
    policy = WireGuardRecoveryPolicy()

    with pytest.raises(ValueError, match="greater than or equal to 1"):
        policy.plan(
            status=WireGuardHealthStatus.FAILED,
            recovery_required=True,
            attempt=0,
            reason="handshake_timeout",
        )
