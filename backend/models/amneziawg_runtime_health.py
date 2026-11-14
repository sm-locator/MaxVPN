from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AmneziaWGRuntimeHealth:
    interface_exists: bool
    interface_up: bool

    expected_peer_found: bool
    expected_endpoint: bool

    listen_port: int | None
    latest_handshake: datetime | None
    rx_bytes: int
    tx_bytes: int

    endpoint_route_ok: bool

    healthy: bool
    reason: str | None
    checked_at: datetime
