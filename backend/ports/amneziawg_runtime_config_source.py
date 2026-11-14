from __future__ import annotations

from abc import ABC, abstractmethod


class AmneziaWGRuntimeConfigSource(ABC):
    @abstractmethod
    def read(
        self,
        interface: str = "WireGuard",
    ) -> str:
        raise NotImplementedError
