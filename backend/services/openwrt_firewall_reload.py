from __future__ import annotations

from dataclasses import dataclass

from backend.infrastructure.openwrt.openwrt_firewall_verifier import (
    OpenWrtFirewallVerificationResult,
    OpenWrtFirewallVerifier,
)
from backend.ports.remote_command_executor import RemoteCommandExecutor


@dataclass(frozen=True, slots=True)
class OpenWrtFirewallReloadResult:
    reload_returncode: int
    reload_succeeded: bool
    verification: OpenWrtFirewallVerificationResult
    healthy: bool
    reason: str | None = None

    @property
    def degraded(self) -> bool:
        return self.reload_returncode != 0 and self.verification.healthy


class OpenWrtFirewallReloadService:
    """
    Reloads fw3 and evaluates the actual MaxVPN firewall state.

    A non-zero fw3 exit code is not automatically considered a MaxVPN
    failure. The runtime firewall state is authoritative for MaxVPN.
    """

    def __init__(
        self,
        executor: RemoteCommandExecutor,
        verifier: OpenWrtFirewallVerifier,
    ) -> None:
        self._executor = executor
        self._verifier = verifier

    def reload(self) -> OpenWrtFirewallReloadResult:
        reload_result = self._executor.run(
            [
                "fw3",
                "reload",
            ]
        )

        verification = self._verifier.verify()

        if verification.healthy:
            if reload_result.returncode == 0:
                return OpenWrtFirewallReloadResult(
                    reload_returncode=reload_result.returncode,
                    reload_succeeded=True,
                    verification=verification,
                    healthy=True,
                    reason=None,
                )

            return OpenWrtFirewallReloadResult(
                reload_returncode=reload_result.returncode,
                reload_succeeded=False,
                verification=verification,
                healthy=True,
                reason=("fw3_reload_returned_nonzero_but_maxvpn_firewall_is_healthy"),
            )

        reason = verification.reason or "maxvpn_firewall_verification_failed"

        return OpenWrtFirewallReloadResult(
            reload_returncode=reload_result.returncode,
            reload_succeeded=reload_result.returncode == 0,
            verification=verification,
            healthy=False,
            reason=reason,
        )
