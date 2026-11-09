from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandResult:
    """
    Result of a command executed on a remote system.
    """

    stdout: str
    stderr: str
    returncode: int
