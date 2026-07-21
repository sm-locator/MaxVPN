from __future__ import annotations

from dataclasses import dataclass

from app.vpn.executors import CommandExecutor


@dataclass(slots=True, frozen=True)
class WireGuardKeyPair:
    """WireGuard key pair."""

    private_key: str
    public_key: str


class WireGuardKeyGenerationError(Exception):
    """Raised when WireGuard key generation fails."""


class WireGuardKeyGenerator:
    """Generates WireGuard key pairs."""

    def __init__(self, executor: CommandExecutor) -> None:
        self._executor = executor

    def generate(self) -> WireGuardKeyPair:
        private_key = self._executor.run(
            ["wg", "genkey"],
        ).stdout

        public_key = self._executor.run(
            ["wg", "pubkey"],
            input_data=private_key,
        ).stdout

        return WireGuardKeyPair(
            private_key=private_key,
            public_key=public_key,
        )
