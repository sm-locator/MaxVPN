from __future__ import annotations

from typing import Protocol


class CommandExecutor(Protocol):
    def run(
        self,
        command: list[str],
    ) -> None: ...
