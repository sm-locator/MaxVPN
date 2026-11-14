from __future__ import annotations

from abc import ABC, abstractmethod

from backend.models.wireguard_health import WireGuardHealth


class WireGuardHealthChecker(ABC):
    """
    Port for reading the runtime health state of a WireGuard interface.
    """

    @abstractmethod
    def check(self) -> WireGuardHealth:
        """
        Return a snapshot of the current WireGuard health state.
        """
        raise NotImplementedError
