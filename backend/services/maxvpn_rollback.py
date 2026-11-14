from __future__ import annotations

from backend.infrastructure.openwrt.openwrt_firewall_persistence import (
    OpenWrtFirewallPersistence,
)
from backend.models.maxvpn_installation import (
    InstallationPhase,
    InstallationStatus,
    InstallationStepResult,
)


class MaxVPNRollbackService:
    """
    Rolls back MaxVPN changes that were already applied during installation.

    The current rollback scope is the persistent OpenWrt firewall installation.
    """

    def __init__(
        self,
        persistence: OpenWrtFirewallPersistence,
    ) -> None:
        self._persistence = persistence

    def execute(self) -> InstallationStepResult:
        try:
            self._persistence.uninstall()
        except Exception as exc:
            return InstallationStepResult(
                phase=InstallationPhase.ROLLBACK,
                status=InstallationStatus.FAILED,
                reason=f"firewall_rollback_failed: {exc}",
            )

        return InstallationStepResult(
            phase=InstallationPhase.ROLLBACK,
            status=InstallationStatus.SUCCESS,
        )
