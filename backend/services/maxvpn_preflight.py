from __future__ import annotations

from pathlib import Path

from backend.application.context.maxvpn_installation_context import (
    MaxVPNInstallationContext,
)
from backend.infrastructure.openwrt.openwrt_network_discovery import (
    OpenWrtNetworkDiscovery,
)
from backend.models.maxvpn_installation import (
    InstallationPhase,
    InstallationStatus,
    InstallationStepResult,
)
from backend.ports.remote_command_executor import RemoteCommandExecutor


class MaxVPNPreflightService:
    """
    Validates that the environment is ready for MaxVPN installation.

    The service is read-only: it must not modify firewall, WireGuard,
    persistence files, or any other router state.
    """

    FIREWALL_USER = "/etc/firewall.user"

    def __init__(
        self,
        executor: RemoteCommandExecutor,
        private_key_path: str,
        discovery: OpenWrtNetworkDiscovery,
        context: MaxVPNInstallationContext,
        dynamic_health_check_factory,
    ) -> None:
        self._executor = executor
        self._private_key_path = Path(private_key_path).expanduser()
        self._discovery = discovery
        self._context = context
        self._dynamic_health_check_factory = dynamic_health_check_factory

    def execute(self) -> InstallationStepResult:
        checks = (
            self._check_private_key,
            self._check_ssh_connectivity,
            self._check_firewall_user,
            self._check_network_discovery,
            self._check_wireguard_interface,
            self._check_wireguard_health,
        )

        for check in checks:
            result = check()

            if result.status == InstallationStatus.FAILED:
                return result

        return self._success()

    def _check_private_key(self) -> InstallationStepResult:
        if not self._private_key_path.is_file():
            return self._failed("ssh_private_key_not_found")

        return self._success()

    def _check_ssh_connectivity(self) -> InstallationStepResult:
        result = self._executor.run(
            [
                "true",
            ]
        )

        if result.returncode != 0:
            return self._failed("ssh_connectivity_failed")

        return self._success()

    def _check_firewall_user(self) -> InstallationStepResult:
        result = self._executor.run(
            [
                "test",
                "-f",
                self.FIREWALL_USER,
            ]
        )

        if result.returncode != 0:
            return self._failed("firewall_user_missing")

        return self._success()

    def _check_wireguard_interface(self) -> InstallationStepResult:
        interface_name = (
            self._context.network.vpn_interface
            if self._context.network is not None
            else None
        )

        if not interface_name:
            return self._failed("wireguard_interface_missing")

        self._wireguard_interface = interface_name

        result = self._executor.run(
            [
                "ip",
                "link",
                "show",
                "dev",
                interface_name,
            ]
        )

        if result.returncode != 0:
            return self._failed("wireguard_interface_missing")

        return self._success()

    def _check_network_discovery(self) -> InstallationStepResult:
        try:
            self._context.network = self._discovery.discover()
        except Exception:
            return self._failed("network_discovery_failed")

        return self._success()

    def _check_wireguard_health(self) -> InstallationStepResult:
        interface_name = (
            self._context.network.vpn_interface
            if self._context.network is not None
            else None
        )

        if not interface_name:
            return self._failed("wireguard_interface_missing")

        try:
            health_check = self._dynamic_health_check_factory(
                interface_name,
            )
            health = health_check.execute()
        except Exception:
            return self._failed("wireguard_health_check_failed")

        if not health.interface_exists:
            return self._failed("wireguard_interface_missing")

        if not health.interface_up:
            return self._failed("wireguard_interface_down")

        return self._success()

    @staticmethod
    def _success() -> InstallationStepResult:
        return InstallationStepResult(
            phase=InstallationPhase.PREFLIGHT,
            status=InstallationStatus.SUCCESS,
        )

    @staticmethod
    def _failed(
        reason: str,
    ) -> InstallationStepResult:
        return InstallationStepResult(
            phase=InstallationPhase.PREFLIGHT,
            status=InstallationStatus.FAILED,
            reason=reason,
        )
