from __future__ import annotations

from abc import ABC, abstractmethod

from backend.models.amneziawg_config import AmneziaWGConfig


class AmneziaWGConfigPersistence(ABC):
    """Port for persisting AmneziaWG configuration on the router."""

    @abstractmethod
    def persist(self, config: AmneziaWGConfig) -> None:
        raise NotImplementedError
