from __future__ import annotations

from abc import ABC, abstractmethod

from backend.models.amneziawg_runtime_snapshot import (
    AmneziaWGRuntimeSnapshot,
)


class AmneziaWGRuntimeSnapshotPort(ABC):
    @abstractmethod
    def capture(
        self,
        interface: str,
    ) -> AmneziaWGRuntimeSnapshot:
        raise NotImplementedError

    @abstractmethod
    def restore(
        self,
        snapshot: AmneziaWGRuntimeSnapshot,
    ) -> None:
        raise NotImplementedError
