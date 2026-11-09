from __future__ import annotations

from backend.application.use_cases.monitor_wireguard import (
    MonitorWireGuardUseCase,
)
from backend.application.use_cases.recover_wireguard import (
    RecoverWireGuardUseCase,
)
from backend.models.wireguard_monitoring_recovery_result import (
    WireGuardMonitoringRecoveryResult,
)
from backend.models.wireguard_recovery import WireGuardRecoveryAction
from backend.services.wireguard_recovery_policy import WireGuardRecoveryPolicy


class MonitorAndRecoverWireGuardUseCase:
    """
    Runs monitoring and, when required, performs one recovery attempt.
    """

    def __init__(
        self,
        monitor: MonitorWireGuardUseCase,
        recovery_policy: WireGuardRecoveryPolicy,
        recovery: RecoverWireGuardUseCase,
    ) -> None:
        self._monitor = monitor
        self._recovery_policy = recovery_policy
        self._recovery = recovery
        self._recovery_attempt = 0

    @property
    def recovery_attempt(self) -> int:
        return self._recovery_attempt

    def execute(self) -> WireGuardMonitoringRecoveryResult:
        monitoring = self._monitor.execute()

        if not monitoring.recovery_required:
            self._recovery_attempt = 0

            return WireGuardMonitoringRecoveryResult(
                monitoring=monitoring,
                recovery_plan=None,
                recovery=None,
            )

        self._recovery_attempt += 1

        plan = self._recovery_policy.plan(
            status=monitoring.state.status,
            recovery_required=True,
            attempt=self._recovery_attempt,
            reason=monitoring.health.reason,
        )

        if plan.action is WireGuardRecoveryAction.NONE:
            return WireGuardMonitoringRecoveryResult(
                monitoring=monitoring,
                recovery_plan=plan,
                recovery=None,
            )

        recovery_result = self._recovery.execute(plan)

        if recovery_result.recovered:
            self._recovery_attempt = 0

        return WireGuardMonitoringRecoveryResult(
            monitoring=monitoring,
            recovery_plan=plan,
            recovery=recovery_result,
        )
