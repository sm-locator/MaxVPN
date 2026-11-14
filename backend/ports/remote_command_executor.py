from __future__ import annotations

from abc import ABC, abstractmethod

from backend.models.command_result import CommandResult


class RemoteCommandExecutor(ABC):
    """
    Port for executing commands on a remote machine.
    """

    @abstractmethod
    def run(
        self,
        command: list[str],
        stdin: str | None = None,
    ) -> CommandResult:
        """
        Execute a command remotely and return its result.

        Optional ``stdin`` is sent to the remote process.
        """
        raise NotImplementedError
