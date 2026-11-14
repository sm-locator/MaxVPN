from __future__ import annotations

from backend.application.use_cases.check_wireguard_health import (
    CheckWireGuardHealthUseCase,
)
from backend.models.maxvpn_installation import (
    InstallationPhase,
    InstallationStatus,
    InstallationStepResult,
)


class MaxVPNWireGuardInstallationService:
    """
    Adapts the existing WireGuard health check to the installation domain.

    A transient degraded health state gets one immediate re-check. This
    avoids failing installation because the handshake happened just before
    the first health sample became stale.
    """

    def __init__(
        self,
        health_check: CheckWireGuardHealthUseCase,
    ) -> None:
        self._health_check = health_check

    def execute(self) -> InstallationStepResult:
        try:
            health = self._health_check.execute()
        except Exception as exc:
            return self._failed(f"wireguard_health_check_failed: {exc}")

        if not health.interface_exists:
            return self._failed("wireguard_interface_missing")

        if not health.interface_up:
            return self._failed("wireguard_interface_down")

        if health.status.value == "healthy":
            return self._success()

        if health.status.value == "degraded":
            return self._recheck_degraded()

        return self._failed(health.reason or "wireguard_health_failed")

    def _recheck_degraded(self) -> InstallationStepResult:
        try:
            health = self._health_check.execute()
        except Exception as exc:
            return self._degraded(f"wireguard_health_recheck_failed: {exc}")

        if not health.interface_exists:
            return self._failed("wireguard_interface_missing")

        if not health.interface_up:
            return self._failed("wireguard_interface_down")

        if health.status.value == "healthy":
            return self._success()

        if health.status.value == "degraded":
            return self._degraded(health.reason or "wireguard_health_degraded")

        return self._failed(health.reason or "wireguard_health_failed")

    @staticmethod
    def _success() -> InstallationStepResult:
        return InstallationStepResult(
            phase=InstallationPhase.WIREGUARD,
            status=InstallationStatus.SUCCESS,
        )

    @staticmethod
    def _degraded(
        reason: str,
    ) -> InstallationStepResult:
        return InstallationStepResult(
            phase=InstallationPhase.WIREGUARD,
            status=InstallationStatus.DEGRADED,
            reason=reason,
        )

    @staticmethod
    def _failed(
        reason: str,
    ) -> InstallationStepResult:
        return InstallationStepResult(
            phase=InstallationPhase.WIREGUARD,
            status=InstallationStatus.FAILED,
            reason=reason,
        )
