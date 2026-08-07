from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class ServerMetrics:
    """
    Dynamic server metrics.

    These values are expected to change frequently.
    """

    cpu_load: float = 0.0
    latency: float = 0.0
    packet_loss: float = 0.0

    active_clients: int = 0

    bandwidth_usage: float = 0.0

    last_updated: datetime | None = None
