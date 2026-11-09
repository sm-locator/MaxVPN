from __future__ import annotations

from backend.application.use_cases.check_wireguard_health import (
    CheckWireGuardHealthUseCase,
)
from backend.models.wireguard_health import WireGuardHealthStatus
from backend.models.wireguard_monitoring_result import WireGuardMonitoringResult
from backend.services.wireguard_monitor import WireGuardMonitor


class MonitorWireGuardUseCase:
    """
    Executes one health-check cycle and updates monitoring state.
    """

    def __init__(
        self,
        health_check: CheckWireGuardHealthUseCase,
        monitor: WireGuardMonitor,
    ) -> None:
        self._health_check = health_check
        self._monitor = monitor

    def execute(self) -> WireGuardMonitoringResult:
        health = self._health_check.execute()

        state = self._monitor.update(
            status=health.status,
            checked_at=health.checked_at,
        )

        recovery_required = state.status is WireGuardHealthStatus.FAILED

        return WireGuardMonitoringResult(
            health=health,
            state=state,
            recovery_required=recovery_required,
        )
