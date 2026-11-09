from __future__ import annotations

from backend.models.wireguard_recovery import (
    WireGuardRecoveryAction,
    WireGuardRecoveryPlan,
)
from backend.ports.remote_command_executor import RemoteCommandExecutor
from backend.ports.wireguard_recovery_executor import (
    WireGuardRecoveryExecutor,
)


class SSHWireGuardRecoveryExecutor(WireGuardRecoveryExecutor):
    """
    Builds and optionally executes WireGuard recovery commands remotely.
    """

    def __init__(
        self,
        executor: RemoteCommandExecutor,
        interface_name: str,
    ) -> None:
        self._executor = executor
        self._interface_name = interface_name

    def build_commands(
        self,
        plan: WireGuardRecoveryPlan,
    ) -> list[list[str]]:
        if plan.action is WireGuardRecoveryAction.NONE:
            return []

        if plan.action is WireGuardRecoveryAction.RESTART_INTERFACE:
            return [
                ["ifdown", self._interface_name],
                ["ifup", self._interface_name],
            ]

        raise ValueError(f"Unsupported WireGuard recovery action: {plan.action}")

    def execute(self, plan: WireGuardRecoveryPlan) -> None:
        commands = self.build_commands(plan)

        for command in commands:
            result = self._executor.run(command)

            if result.returncode != 0:
                raise RuntimeError(
                    "WireGuard recovery command failed: "
                    f"{command!r}; "
                    f"returncode={result.returncode}; "
                    f"stderr={result.stderr!r}"
                )
