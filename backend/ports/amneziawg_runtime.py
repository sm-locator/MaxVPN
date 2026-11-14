from __future__ import annotations

from abc import ABC, abstractmethod

from backend.models.amneziawg_config import AmneziaWGConfig


class AmneziaWGRuntimePort(ABC):
    """Port for planning and applying an AmneziaWG runtime configuration."""

    @abstractmethod
    def plan(
        self,
        config: AmneziaWGConfig,
        interface: str = "WireGuard",
    ) -> str:
        """Build an awg syncconf command without executing it."""
        raise NotImplementedError

    @abstractmethod
    def apply(
        self,
        config: AmneziaWGConfig,
        interface: str = "WireGuard",
    ) -> None:
        """Apply the runtime configuration."""
        raise NotImplementedError
