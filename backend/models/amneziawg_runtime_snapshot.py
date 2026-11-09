from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AmneziaWGRuntimeSnapshot:
    interface: str
    config_text: str
