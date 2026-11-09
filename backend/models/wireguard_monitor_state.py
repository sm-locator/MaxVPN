from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.models.wireguard_health import WireGuardHealthStatus


@dataclass(frozen=True, slots=True)
class WireGuardMonitorState:
    """
    Runtime monitoring state for a WireGuard health stream.
    """

    status: WireGuardHealthStatus
    consecutive_failures: int
    consecutive_degraded: int
    last_status_change: datetime
    last_check_at: datetime
