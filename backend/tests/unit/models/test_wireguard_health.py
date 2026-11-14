from datetime import datetime, timezone

from backend.models.wireguard_health import (
    WireGuardHealth,
    WireGuardHealthStatus,
)


def test_wireguard_health_can_store_healthy_snapshot() -> None:
    checked_at = datetime.now(timezone.utc)

    health = WireGuardHealth(
        interface_exists=True,
        interface_up=True,
        listen_port=51820,
        peer_count=2,
        latest_handshake=checked_at,
        rx_bytes=1024,
        tx_bytes=2048,
        status=WireGuardHealthStatus.HEALTHY,
        reason=None,
        checked_at=checked_at,
    )

    assert health.interface_exists is True
    assert health.interface_up is True
    assert health.listen_port == 51820
    assert health.peer_count == 2
    assert health.latest_handshake == checked_at
    assert health.rx_bytes == 1024
    assert health.tx_bytes == 2048
    assert health.status is WireGuardHealthStatus.HEALTHY
    assert health.reason is None
    assert health.checked_at == checked_at


def test_wireguard_health_status_has_expected_values() -> None:
    assert WireGuardHealthStatus.UNKNOWN.value == "unknown"
    assert WireGuardHealthStatus.HEALTHY.value == "healthy"
    assert WireGuardHealthStatus.DEGRADED.value == "degraded"
    assert WireGuardHealthStatus.FAILED.value == "failed"
