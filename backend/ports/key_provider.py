from __future__ import annotations

from abc import ABC, abstractmethod

from backend.models.key_pair import KeyPair


class KeyProvider(ABC):
    """
    Generates WireGuard-compatible key pairs.
    """

    @abstractmethod
    def generate(self) -> KeyPair:
        raise NotImplementedError
