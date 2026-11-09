from __future__ import annotations

from abc import ABC, abstractmethod


class WireGuardInterfaceLifecycle(ABC):
    """Remote lifecycle operations for a WireGuard/AmneziaWG interface."""

    @abstractmethod
    def exists(self, interface: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def bring_up(self, interface: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def bring_down(self, interface: str) -> None:
        raise NotImplementedError
