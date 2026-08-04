from __future__ import annotations

import subprocess

from app.infrastructure.executor import CommandExecutor


class LocalCommandExecutor(CommandExecutor):
    def run(
        self,
        command: list[str],
    ) -> None:
        subprocess.run(
            command,
            check=True,
        )
