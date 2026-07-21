from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


class CommandExecutor(ABC):
    """Abstract command executor."""

    @abstractmethod
    def run(
        self,
        command: list[str],
        input_data: str | None = None,
    ) -> CommandResult:
        """Execute command."""
        raise NotImplementedError
