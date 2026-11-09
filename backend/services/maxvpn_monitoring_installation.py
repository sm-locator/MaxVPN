from __future__ import annotations

from backend.application.use_cases.monitor_and_recover_wireguard import (
    MonitorAndRecoverWireGuardUseCase,
)
from backend.models.maxvpn_installation import (
    InstallationPhase,
    InstallationStatus,
    InstallationStepResult,
)
from backend.models.wireguard_health import WireGuardHealthStatus


class MaxVPNMonitoringInstallationService:
    """
    Performs one initial WireGuard monitoring/recovery cycle.

    This service validates that the existing monitoring and recovery
    infrastructure is operational. It does not create a persistent
    background monitoring loop.
    """

    def __init__(
        self,
        monitor_and_recover: MonitorAndRecoverWireGuardUseCase,
    ) -> None:
        self._monitor_and_recover = monitor_and_recover

    def execute(self) -> InstallationStepResult:
        try:
            result = self._monitor_and_recover.execute()
        except Exception as exc:
            return InstallationStepResult(
                phase=InstallationPhase.MONITORING,
                status=InstallationStatus.FAILED,
                reason=f"monitoring_cycle_failed: {exc}",
            )

        health = result.monitoring.health

        if health.status is WireGuardHealthStatus.HEALTHY:
            return InstallationStepResult(
                phase=InstallationPhase.MONITORING,
                status=InstallationStatus.SUCCESS,
            )

        if result.recovery is not None and result.recovery.recovered:
            return InstallationStepResult(
                phase=InstallationPhase.MONITORING,
                status=InstallationStatus.SUCCESS,
            )

        if health.status is WireGuardHealthStatus.DEGRADED:
            return InstallationStepResult(
                phase=InstallationPhase.MONITORING,
                status=InstallationStatus.DEGRADED,
                reason=health.reason or "wireguard_monitoring_degraded",
            )

        return InstallationStepResult(
            phase=InstallationPhase.MONITORING,
            status=InstallationStatus.FAILED,
            reason=health.reason or "wireguard_monitoring_failed",
        )
