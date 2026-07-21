from __future__ import annotations

import subprocess

from app.vpn.executors.base import CommandExecutor, CommandResult


class LocalCommandExecutor(CommandExecutor):
    """Executes commands on the local machine."""

    def run(
        self,
        command: list[str],
        input_data: str | None = None,
    ) -> CommandResult:
        result = subprocess.run(
            command,
            input=input_data,
            capture_output=True,
            text=True,
            check=True,
        )

        return CommandResult(
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
            returncode=result.returncode,
        )
