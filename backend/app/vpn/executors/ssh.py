from __future__ import annotations

from app.vpn.executors.base import CommandExecutor, CommandResult


class SSHCommandExecutor(CommandExecutor):
    """Executes commands on a remote server."""

    def run(
        self,
        command: list[str],
        input_data: str | None = None,
    ) -> CommandResult:
        raise NotImplementedError
