from datetime import datetime, timezone

from backend.models.wireguard_health import (
    WireGuardHealth,
    WireGuardHealthStatus,
)
from backend.ports.wireguard_health_checker import WireGuardHealthChecker


class StubWireGuardHealthChecker(WireGuardHealthChecker):
    def __init__(self, health: WireGuardHealth) -> None:
        self._health = health

    def check(self) -> WireGuardHealth:
        return self._health


def test_wireguard_health_checker_returns_health_snapshot() -> None:
    checked_at = datetime.now(timezone.utc)

    expected = WireGuardHealth(
        interface_exists=True,
        interface_up=True,
        listen_port=51820,
        peer_count=1,
        latest_handshake=checked_at,
        rx_bytes=100,
        tx_bytes=200,
        status=WireGuardHealthStatus.HEALTHY,
        reason=None,
        checked_at=checked_at,
    )

    checker = StubWireGuardHealthChecker(expected)

    assert checker.check() == expected
