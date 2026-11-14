from __future__ import annotations

from abc import ABC, abstractmethod

from backend.models.amneziawg_config import AmneziaWGConfig


class AmneziaWGConfigSource(ABC):
    @abstractmethod
    def read(self) -> AmneziaWGConfig:
        raise NotImplementedError
