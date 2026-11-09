from datetime import datetime, timezone
from unittest.mock import Mock

from backend.application.use_cases.check_wireguard_health import (
    CheckWireGuardHealthUseCase,
)
from backend.application.use_cases.recover_wireguard import (
    RecoverWireGuardUseCase,
)
from backend.models.wireguard_health import (
    WireGuardHealth,
    WireGuardHealthStatus,
)
from backend.models.wireguard_recovery import (
    WireGuardRecoveryAction,
    WireGuardRecoveryPlan,
)
from backend.ports.wireguard_recovery_executor import (
    WireGuardRecoveryExecutor,
)


def make_health(status: WireGuardHealthStatus) -> WireGuardHealth:
    checked_at = datetime.now(timezone.utc)

    return WireGuardHealth(
        interface_exists=True,
        interface_up=True,
        listen_port=45121,
        peer_count=1,
        latest_handshake=checked_at,
        rx_bytes=100,
        tx_bytes=200,
        status=status,
        reason=None,
        checked_at=checked_at,
    )


def make_plan(
    action: WireGuardRecoveryAction,
    backoff_seconds: int = 5,
    attempt: int = 1,
) -> WireGuardRecoveryPlan:
    return WireGuardRecoveryPlan(
        action=action,
        attempt=attempt,
        max_attempts=3,
        backoff_seconds=backoff_seconds,
        reason="handshake_timeout",
    )


def test_failed_recovery_waits_then_recovers() -> None:
    recovery_executor = Mock(spec=WireGuardRecoveryExecutor)
    health_check = Mock(spec=CheckWireGuardHealthUseCase)
    sleeper = Mock()

    healthy = make_health(WireGuardHealthStatus.HEALTHY)
    health_check.execute.return_value = healthy

    use_case = RecoverWireGuardUseCase(
        recovery_executor=recovery_executor,
        health_check=health_check,
        sleeper=sleeper,
    )

    plan = make_plan(
        WireGuardRecoveryAction.RESTART_INTERFACE,
        backoff_seconds=5,
        attempt=1,
    )

    result = use_case.execute(plan)

    assert result.recovered is True

    sleeper.assert_called_once_with(5)
    recovery_executor.execute.assert_called_once_with(plan)
    health_check.execute.assert_called_once_with()


def test_second_attempt_uses_fifteen_second_backoff() -> None:
    recovery_executor = Mock(spec=WireGuardRecoveryExecutor)
    health_check = Mock(spec=CheckWireGuardHealthUseCase)
    sleeper = Mock()

    health_check.execute.return_value = make_health(
        WireGuardHealthStatus.FAILED,
    )

    use_case = RecoverWireGuardUseCase(
        recovery_executor=recovery_executor,
        health_check=health_check,
        sleeper=sleeper,
    )

    plan = make_plan(
        WireGuardRecoveryAction.RESTART_INTERFACE,
        backoff_seconds=15,
        attempt=2,
    )

    result = use_case.execute(plan)

    assert result.recovered is False
    sleeper.assert_called_once_with(15)
    recovery_executor.execute.assert_called_once_with(plan)


def test_third_attempt_uses_thirty_second_backoff() -> None:
    recovery_executor = Mock(spec=WireGuardRecoveryExecutor)
    health_check = Mock(spec=CheckWireGuardHealthUseCase)
    sleeper = Mock()

    health_check.execute.return_value = make_health(
        WireGuardHealthStatus.FAILED,
    )

    use_case = RecoverWireGuardUseCase(
        recovery_executor=recovery_executor,
        health_check=health_check,
        sleeper=sleeper,
    )

    plan = make_plan(
        WireGuardRecoveryAction.RESTART_INTERFACE,
        backoff_seconds=30,
        attempt=3,
    )

    result = use_case.execute(plan)

    assert result.recovered is False
    sleeper.assert_called_once_with(30)
    recovery_executor.execute.assert_called_once_with(plan)


def test_none_recovery_does_not_sleep_or_execute() -> None:
    recovery_executor = Mock(spec=WireGuardRecoveryExecutor)
    health_check = Mock(spec=CheckWireGuardHealthUseCase)
    sleeper = Mock()

    health_check.execute.return_value = make_health(
        WireGuardHealthStatus.HEALTHY,
    )

    use_case = RecoverWireGuardUseCase(
        recovery_executor=recovery_executor,
        health_check=health_check,
        sleeper=sleeper,
    )

    plan = make_plan(
        WireGuardRecoveryAction.NONE,
        backoff_seconds=0,
    )

    result = use_case.execute(plan)

    assert result.recovered is True
    sleeper.assert_not_called()
    recovery_executor.execute.assert_not_called()
    health_check.execute.assert_called_once_with()


def test_zero_backoff_does_not_sleep() -> None:
    recovery_executor = Mock(spec=WireGuardRecoveryExecutor)
    health_check = Mock(spec=CheckWireGuardHealthUseCase)
    sleeper = Mock()

    health_check.execute.return_value = make_health(
        WireGuardHealthStatus.HEALTHY,
    )

    use_case = RecoverWireGuardUseCase(
        recovery_executor=recovery_executor,
        health_check=health_check,
        sleeper=sleeper,
    )

    plan = make_plan(
        WireGuardRecoveryAction.RESTART_INTERFACE,
        backoff_seconds=0,
    )

    result = use_case.execute(plan)

    assert result.recovered is True
    sleeper.assert_not_called()
    recovery_executor.execute.assert_called_once_with(plan)


def test_recovery_still_fails_after_restart() -> None:
    recovery_executor = Mock(spec=WireGuardRecoveryExecutor)
    health_check = Mock(spec=CheckWireGuardHealthUseCase)
    sleeper = Mock()

    health_check.execute.return_value = make_health(
        WireGuardHealthStatus.DEGRADED,
    )

    use_case = RecoverWireGuardUseCase(
        recovery_executor=recovery_executor,
        health_check=health_check,
        sleeper=sleeper,
    )

    plan = make_plan(
        WireGuardRecoveryAction.RESTART_INTERFACE,
        backoff_seconds=5,
    )

    result = use_case.execute(plan)

    assert result.recovered is False
    assert result.health.status is WireGuardHealthStatus.DEGRADED

    sleeper.assert_called_once_with(5)
    recovery_executor.execute.assert_called_once_with(plan)
    health_check.execute.assert_called_once_with()
