from __future__ import annotations

from abc import ABC, abstractmethod


class AddressAllocator(ABC):
    """
    Allocates VPN client addresses.
    """

    @abstractmethod
    def allocate(self) -> str:
        raise NotImplementedError
