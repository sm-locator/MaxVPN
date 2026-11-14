from __future__ import annotations

from backend.ports.remote_command_executor import RemoteCommandExecutor
from backend.ports.wireguard_interface_lifecycle import (
    WireGuardInterfaceLifecycle,
)


class SSHWireGuardInterfaceLifecycle(
    WireGuardInterfaceLifecycle,
):
    def __init__(
        self,
        executor: RemoteCommandExecutor,
    ) -> None:
        self._executor = executor

    def exists(self, interface: str) -> bool:
        if not interface:
            raise ValueError("interface must not be empty")

        result = self._executor.run(
            [
                "ip",
                "link",
                "show",
                "dev",
                interface,
            ]
        )

        return result.returncode == 0

    def bring_up(self, interface: str) -> None:
        if not interface:
            raise ValueError("interface must not be empty")

        result = self._executor.run(
            ["ifup", interface],
        )

        if result.returncode != 0:
            raise RuntimeError(
                "WireGuard interface startup failed: "
                f"returncode={result.returncode}; "
                f"stderr={result.stderr!r}"
            )

    def bring_down(self, interface: str) -> None:
        if not interface:
            raise ValueError("interface must not be empty")

        result = self._executor.run(
            ["ifdown", interface],
        )

        if result.returncode != 0:
            raise RuntimeError(
                "WireGuard interface shutdown failed: "
                f"returncode={result.returncode}; "
                f"stderr={result.stderr!r}"
            )
