from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from backend.models.wireguard_health import (
    WireGuardHealth,
    WireGuardHealthStatus,
)


@dataclass(frozen=True, slots=True)
class WireGuardHealthPolicy:
    """
    Application policy for interpreting a WireGuard health snapshot.
    """

    healthy_handshake_after: timedelta = timedelta(seconds=90)
    failed_handshake_after: timedelta = timedelta(seconds=300)
    now_provider: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    def evaluate(self, health: WireGuardHealth) -> WireGuardHealth:
        now = self.now_provider()

        if not health.interface_exists:
            return self._with_status(
                health,
                WireGuardHealthStatus.FAILED,
                "interface_not_found",
            )

        if not health.interface_up:
            return self._with_status(
                health,
                WireGuardHealthStatus.FAILED,
                "interface_down",
            )

        if health.listen_port is None:
            return self._with_status(
                health,
                WireGuardHealthStatus.FAILED,
                "listen_port_unavailable",
            )

        if health.peer_count == 0:
            return self._with_status(
                health,
                WireGuardHealthStatus.DEGRADED,
                "no_peers",
            )

        if health.latest_handshake is None:
            return self._with_status(
                health,
                WireGuardHealthStatus.DEGRADED,
                "no_handshake",
            )

        handshake_age = now - health.latest_handshake

        if handshake_age < timedelta(0):
            handshake_age = timedelta(0)

        if handshake_age <= self.healthy_handshake_after:
            return self._with_status(
                health,
                WireGuardHealthStatus.HEALTHY,
                None,
            )

        if handshake_age <= self.failed_handshake_after:
            return self._with_status(
                health,
                WireGuardHealthStatus.DEGRADED,
                "stale_handshake",
            )

        return self._with_status(
            health,
            WireGuardHealthStatus.FAILED,
            "handshake_timeout",
        )

    @staticmethod
    def _with_status(
        health: WireGuardHealth,
        status: WireGuardHealthStatus,
        reason: str | None,
    ) -> WireGuardHealth:
        return WireGuardHealth(
            interface_exists=health.interface_exists,
            interface_up=health.interface_up,
            listen_port=health.listen_port,
            peer_count=health.peer_count,
            latest_handshake=health.latest_handshake,
            rx_bytes=health.rx_bytes,
            tx_bytes=health.tx_bytes,
            status=status,
            reason=reason,
            checked_at=health.checked_at,
        )
