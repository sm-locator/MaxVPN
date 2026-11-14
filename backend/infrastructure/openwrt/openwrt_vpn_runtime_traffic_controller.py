from __future__ import annotations

import time
from collections.abc import Callable

from backend.ports.remote_command_executor import RemoteCommandExecutor


class OpenWrtVpnRuntimeTrafficController:
    """Switches LAN traffic mode through verified Brume helper scripts."""

    VPN_LAN_ON_SCRIPT = "/usr/bin/vpn-lan-on"
    VPN_LAN_OFF_SCRIPT = "/usr/bin/vpn-lan-off"
    VPN_LAN_VLESS_ON_SCRIPT = "/usr/bin/vpn-lan-vless-on"
    RUNTIME_MODE_FILE = "/etc/maxvpn/runtime-mode"

    def __init__(
        self,
        executor: RemoteCommandExecutor,
        firewall_installer: Callable[[], object] | None = None,
        firewall_watchdog_starter: Callable[[], object] | None = None,
    ) -> None:
        self._executor = executor
        self._firewall_installer = firewall_installer
        self._firewall_watchdog_starter = firewall_watchdog_starter

    def enable_vpn_mode(self) -> None:
        self._run_checked([self.VPN_LAN_ON_SCRIPT])

    def enable_wan_mode(self) -> None:
        self._run_checked([self.VPN_LAN_OFF_SCRIPT])

    def enable_vless_mode(self) -> str | None:
        if self._firewall_installer is None:
            raise RuntimeError(
                "VLESS LAN mode support is not configured; "
                "firewall installer is missing"
            )
        # Prepare support files and stop the previous watchdog before changing
        # the runtime policy. The watchdog is started after the helper returns.
        self._firewall_installer()
        try:
            self._run_checked([self.VPN_LAN_VLESS_ON_SCRIPT])
        except Exception as activation_error:
            if self._firewall_watchdog_starter is not None:
                try:
                    self._firewall_watchdog_starter()
                except Exception as watchdog_error:
                    raise RuntimeError(
                        "VLESS LAN activation failed and the watchdog "
                        "could not be started: "
                        f"activation_error={activation_error!r}; "
                        f"watchdog_error={watchdog_error!r}"
                    ) from activation_error
            raise
        if self._firewall_watchdog_starter is None:
            return "VLESS watchdog starter is not configured"

        try:
            self._firewall_watchdog_starter()
        except Exception as watchdog_error:
            # The LAN helper has already activated and verified VLESS routing.
            # Do not report the activation itself as failed or roll routing back
            # merely because the separate recovery watchdog did not start.
            return f"VLESS watchdog failed to start: {watchdog_error!r}"

        return None

    def get_mode(self) -> str:
        command = ["cat", self.RUNTIME_MODE_FILE]
        result = self._executor.run(command)

        transient_markers = (
            "connection closed by",
            "connection reset by",
            "connection timed out",
            "broken pipe",
        )
        detail = str(getattr(result, "stderr", "") or "").lower()
        if result.returncode != 0 and any(
            marker in detail for marker in transient_markers
        ):
            time.sleep(0.2)
            result = self._executor.run(command)

        if result.returncode != 0:
            raise RuntimeError(
                "OpenWrt VPN runtime traffic mode read failed: "
                f"returncode={result.returncode}; "
                f"stderr={result.stderr!r}",
            )

        mode = result.stdout.strip()

        if mode not in {"vpn", "wan", "vless"}:
            raise RuntimeError(
                f"OpenWrt VPN runtime traffic mode is invalid: {mode!r}",
            )

        return mode

    def _run_checked(self, command: list[str]) -> None:
        result = self._executor.run(command)

        if result.returncode != 0:
            raise RuntimeError(
                "OpenWrt VPN runtime traffic command failed: "
                f"returncode={result.returncode}; "
                f"stderr={result.stderr!r}",
            )
