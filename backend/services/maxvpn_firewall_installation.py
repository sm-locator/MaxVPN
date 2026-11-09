from __future__ import annotations

from backend.infrastructure.openwrt.openwrt_firewall_persistence import (
    OpenWrtFirewallPersistence,
)
from backend.models.maxvpn_installation import (
    InstallationPhase,
    InstallationStatus,
    InstallationStepResult,
)
from backend.models.vpn_traffic_policy import VpnTrafficPolicy


class MaxVPNFirewallInstallationService:
    """
    Adapts the OpenWrt persistence workflow to the installation domain.
    """

    def __init__(
        self,
        persistence: OpenWrtFirewallPersistence,
        policy: VpnTrafficPolicy,
    ) -> None:
        self._persistence = persistence
        self._policy = policy

    def execute(self) -> InstallationStepResult:
        try:
            result = self._persistence.install(
                self._policy,
            )
        except Exception as exc:
            return InstallationStepResult(
                phase=InstallationPhase.FIREWALL,
                status=InstallationStatus.FAILED,
                reason=f"firewall_installation_failed: {exc}",
            )

        if result is not None and result.degraded:
            return InstallationStepResult(
                phase=InstallationPhase.FIREWALL,
                status=InstallationStatus.DEGRADED,
                reason=result.reason,
            )

        return InstallationStepResult(
            phase=InstallationPhase.FIREWALL,
            status=InstallationStatus.SUCCESS,
        )
