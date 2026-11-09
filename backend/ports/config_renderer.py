from __future__ import annotations

from abc import ABC, abstractmethod

from backend.models.client_config import ClientConfig


class ConfigRenderer(ABC):
    """
    Converts ClientConfig into a configuration file.
    """

    @abstractmethod
    def render(self, config: ClientConfig) -> str:
        raise NotImplementedError
