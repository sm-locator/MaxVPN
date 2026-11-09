from datetime import datetime, timezone
from unittest.mock import Mock

from backend.application.use_cases.monitor_and_recover_wireguard import (
    MonitorAndRecoverWireGuardUseCase,
)
from backend.application.use_cases.monitor_wireguard import (
    MonitorWireGuardUseCase,
)
from backend.application.use_cases.recover_wireguard import (
    RecoverWireGuardUseCase,
)
from backend.models.wireguard_health import (
    WireGuardHealth,
    WireGuardHealthStatus,
)
from backend.models.wireguard_monitor_state import WireGuardMonitorState
from backend.models.wireguard_monitoring_recovery_result import (
    WireGuardMonitoringRecoveryResult,
)
from backend.models.wireguard_monitoring_result import (
    WireGuardMonitoringResult,
)
from backend.models.wireguard_recovery import (
    WireGuardRecoveryAction,
    WireGuardRecoveryPlan,
)
from backend.models.wireguard_recovery_result import (
    WireGuardRecoveryResult,
)
from backend.services.wireguard_recovery_policy import (
    WireGuardRecoveryPolicy,
)


def make_health(
    status: WireGuardHealthStatus,
    reason: str | None = None,
) -> WireGuardHealth:
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
        reason=reason,
        checked_at=checked_at,
    )


def make_monitoring_result(
    status: WireGuardHealthStatus,
    recovery_required: bool,
    reason: str | None = None,
) -> WireGuardMonitoringResult:
    health = make_health(
        status=status,
        reason=reason,
    )

    state = WireGuardMonitorState(
        status=status,
        consecutive_failures=3 if status is WireGuardHealthStatus.FAILED else 0,
        consecutive_degraded=0,
        last_status_change=health.checked_at,
        last_check_at=health.checked_at,
    )

    return WireGuardMonitoringResult(
        health=health,
        state=state,
        recovery_required=recovery_required,
    )


def make_recovery_result(
    plan: WireGuardRecoveryPlan,
    recovered: bool,
) -> WireGuardRecoveryResult:
    health = make_health(
        WireGuardHealthStatus.HEALTHY if recovered else WireGuardHealthStatus.FAILED
    )

    return WireGuardRecoveryResult(
        plan=plan,
        health=health,
        recovered=recovered,
    )


def test_healthy_monitoring_does_not_trigger_recovery() -> None:
    monitor = Mock(spec=MonitorWireGuardUseCase)
    recovery_policy = Mock(spec=WireGuardRecoveryPolicy)
    recovery = Mock(spec=RecoverWireGuardUseCase)

    monitoring = make_monitoring_result(
        WireGuardHealthStatus.HEALTHY,
        recovery_required=False,
    )
    monitor.execute.return_value = monitoring

    use_case = MonitorAndRecoverWireGuardUseCase(
        monitor=monitor,
        recovery_policy=recovery_policy,
        recovery=recovery,
    )

    result = use_case.execute()

    assert isinstance(result, WireGuardMonitoringRecoveryResult)
    assert result.monitoring is monitoring
    assert result.recovery_plan is None
    assert result.recovery is None
    assert use_case.recovery_attempt == 0

    recovery_policy.plan.assert_not_called()
    recovery.execute.assert_not_called()


def test_failed_monitoring_creates_plan_and_executes_recovery() -> None:
    monitor = Mock(spec=MonitorWireGuardUseCase)
    recovery_policy = Mock(spec=WireGuardRecoveryPolicy)
    recovery = Mock(spec=RecoverWireGuardUseCase)

    monitoring = make_monitoring_result(
        WireGuardHealthStatus.FAILED,
        recovery_required=True,
        reason="handshake_timeout",
    )
    monitor.execute.return_value = monitoring

    plan = WireGuardRecoveryPlan(
        action=WireGuardRecoveryAction.RESTART_INTERFACE,
        attempt=1,
        max_attempts=3,
        backoff_seconds=5,
        reason="handshake_timeout",
    )
    recovery_policy.plan.return_value = plan

    recovery_result = make_recovery_result(
        plan=plan,
        recovered=True,
    )
    recovery.execute.return_value = recovery_result

    use_case = MonitorAndRecoverWireGuardUseCase(
        monitor=monitor,
        recovery_policy=recovery_policy,
        recovery=recovery,
    )

    result = use_case.execute()

    assert result.monitoring is monitoring
    assert result.recovery_plan is plan
    assert result.recovery is recovery_result
    assert result.recovery.recovered is True
    assert use_case.recovery_attempt == 0

    recovery_policy.plan.assert_called_once_with(
        status=WireGuardHealthStatus.FAILED,
        recovery_required=True,
        attempt=1,
        reason="handshake_timeout",
    )
    recovery.execute.assert_called_once_with(plan)


def test_failed_recovery_increments_attempt_count() -> None:
    monitor = Mock(spec=MonitorWireGuardUseCase)
    recovery_policy = Mock(spec=WireGuardRecoveryPolicy)
    recovery = Mock(spec=RecoverWireGuardUseCase)

    monitoring = make_monitoring_result(
        WireGuardHealthStatus.FAILED,
        recovery_required=True,
        reason="handshake_timeout",
    )
    monitor.execute.return_value = monitoring

    plan1 = WireGuardRecoveryPlan(
        action=WireGuardRecoveryAction.RESTART_INTERFACE,
        attempt=1,
        max_attempts=3,
        backoff_seconds=5,
        reason="handshake_timeout",
    )
    plan2 = WireGuardRecoveryPlan(
        action=WireGuardRecoveryAction.RESTART_INTERFACE,
        attempt=2,
        max_attempts=3,
        backoff_seconds=15,
        reason="handshake_timeout",
    )

    recovery_policy.plan.side_effect = [plan1, plan2]

    recovery.execute.side_effect = [
        make_recovery_result(plan1, recovered=False),
        make_recovery_result(plan2, recovered=False),
    ]

    use_case = MonitorAndRecoverWireGuardUseCase(
        monitor=monitor,
        recovery_policy=recovery_policy,
        recovery=recovery,
    )

    first = use_case.execute()
    second = use_case.execute()

    assert first.recovery is not None
    assert first.recovery.recovered is False
    assert second.recovery is not None
    assert second.recovery.recovered is False
    assert use_case.recovery_attempt == 2

    assert recovery_policy.plan.call_args_list[0].kwargs["attempt"] == 1
    assert recovery_policy.plan.call_args_list[1].kwargs["attempt"] == 2


def test_recovery_policy_can_refuse_after_max_attempts() -> None:
    monitor = Mock(spec=MonitorWireGuardUseCase)
    recovery_policy = Mock(spec=WireGuardRecoveryPolicy)
    recovery = Mock(spec=RecoverWireGuardUseCase)

    monitoring = make_monitoring_result(
        WireGuardHealthStatus.FAILED,
        recovery_required=True,
        reason="handshake_timeout",
    )
    monitor.execute.return_value = monitoring

    plan = WireGuardRecoveryPlan(
        action=WireGuardRecoveryAction.NONE,
        attempt=4,
        max_attempts=3,
        backoff_seconds=0,
        reason="max_attempts_exceeded",
    )
    recovery_policy.plan.return_value = plan

    use_case = MonitorAndRecoverWireGuardUseCase(
        monitor=monitor,
        recovery_policy=recovery_policy,
        recovery=recovery,
    )

    use_case._recovery_attempt = 3

    result = use_case.execute()

    assert result.recovery_plan is plan
    assert result.recovery is None
    assert result.recovery_plan.action is WireGuardRecoveryAction.NONE

    recovery.execute.assert_not_called()


def test_successful_recovery_resets_attempt_count() -> None:
    monitor = Mock(spec=MonitorWireGuardUseCase)
    recovery_policy = Mock(spec=WireGuardRecoveryPolicy)
    recovery = Mock(spec=RecoverWireGuardUseCase)

    monitoring = make_monitoring_result(
        WireGuardHealthStatus.FAILED,
        recovery_required=True,
        reason="handshake_timeout",
    )
    monitor.execute.return_value = monitoring

    plan = WireGuardRecoveryPlan(
        action=WireGuardRecoveryAction.RESTART_INTERFACE,
        attempt=3,
        max_attempts=3,
        backoff_seconds=30,
        reason="handshake_timeout",
    )
    recovery_policy.plan.return_value = plan
    recovery.execute.return_value = make_recovery_result(
        plan,
        recovered=True,
    )

    use_case = MonitorAndRecoverWireGuardUseCase(
        monitor=monitor,
        recovery_policy=recovery_policy,
        recovery=recovery,
    )
    use_case._recovery_attempt = 2

    result = use_case.execute()

    assert result.recovery is not None
    assert result.recovery.recovered is True
    assert use_case.recovery_attempt == 0
