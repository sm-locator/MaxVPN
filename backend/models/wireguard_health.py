from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class WireGuardHealthStatus(str, Enum):
    """
    High-level health state of a WireGuard interface.
    """

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass(slots=True)
class WireGuardHealth:
    """
    Snapshot of the current WireGuard health state.
    """

    interface_exists: bool
    interface_up: bool
    listen_port: int | None
    peer_count: int
    latest_handshake: datetime | None
    rx_bytes: int
    tx_bytes: int
    status: WireGuardHealthStatus
    reason: str | None
    checked_at: datetime
