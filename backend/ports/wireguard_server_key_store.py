from __future__ import annotations

from abc import ABC, abstractmethod


class WireGuardServerKeyStore(ABC):
    """Persistent storage for the WireGuard server private key."""

    @abstractmethod
    def exists(self) -> bool:
        """Return whether a server private key exists."""
        raise NotImplementedError

    @abstractmethod
    def read(self) -> str:
        """Read the server private key."""
        raise NotImplementedError

    @abstractmethod
    def write(self, private_key: str) -> None:
        """Persist the server private key."""
        raise NotImplementedError
