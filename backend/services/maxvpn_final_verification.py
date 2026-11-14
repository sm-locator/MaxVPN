from __future__ import annotations

from backend.application.use_cases.check_wireguard_health import (
    CheckWireGuardHealthUseCase,
)
from backend.infrastructure.openwrt.openwrt_firewall_verifier import (
    OpenWrtFirewallVerifier,
)
from backend.models.maxvpn_installation import (
    InstallationPhase,
    InstallationStatus,
    InstallationStepResult,
)


class MaxVPNFinalVerificationService:
    """
    Performs the final installation verification.

    The final verification delegates runtime checks to the existing
    firewall verifier and WireGuard health use case.
    """

    def __init__(
        self,
        firewall_verifier: OpenWrtFirewallVerifier,
        wireguard_health_check: CheckWireGuardHealthUseCase,
    ) -> None:
        self._firewall_verifier = firewall_verifier
        self._wireguard_health_check = wireguard_health_check

    def execute(self) -> InstallationStepResult:
        try:
            firewall = self._firewall_verifier.verify()
        except Exception as exc:
            return self._failed(
                f"firewall_final_verification_failed: {exc}",
            )

        if not firewall.healthy:
            return self._failed(
                firewall.reason or "firewall_final_verification_failed",
            )

        try:
            wireguard = self._wireguard_health_check.execute()
        except Exception as exc:
            return self._failed(
                f"wireguard_final_verification_failed: {exc}",
            )

        status = wireguard.status.value

        if status == "healthy":
            return self._success()

        if status == "degraded":
            return self._degraded(
                wireguard.reason or "wireguard_final_verification_degraded",
            )

        return self._failed(
            wireguard.reason or "wireguard_final_verification_failed",
        )

    @staticmethod
    def _success() -> InstallationStepResult:
        return InstallationStepResult(
            phase=InstallationPhase.FINAL_VERIFY,
            status=InstallationStatus.SUCCESS,
        )

    @staticmethod
    def _degraded(
        reason: str,
    ) -> InstallationStepResult:
        return InstallationStepResult(
            phase=InstallationPhase.FINAL_VERIFY,
            status=InstallationStatus.DEGRADED,
            reason=reason,
        )

    @staticmethod
    def _failed(
        reason: str,
    ) -> InstallationStepResult:
        return InstallationStepResult(
            phase=InstallationPhase.FINAL_VERIFY,
            status=InstallationStatus.FAILED,
            reason=reason,
        )
