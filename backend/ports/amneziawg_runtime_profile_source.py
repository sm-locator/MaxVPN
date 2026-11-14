from __future__ import annotations

from abc import ABC, abstractmethod

from backend.models.amneziawg_config import AmneziaWGConfig


class AmneziaWGRuntimeProfileSource(ABC):
    @abstractmethod
    def read(
        self,
        interface: str = "WireGuard",
    ) -> AmneziaWGConfig:
        raise NotImplementedError
