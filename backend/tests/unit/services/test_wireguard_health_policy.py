from datetime import datetime, timedelta, timezone

from backend.models.wireguard_health import (
    WireGuardHealth,
    WireGuardHealthStatus,
)
from backend.services.wireguard_health_policy import WireGuardHealthPolicy


def make_health(
    *,
    latest_handshake: datetime | None,
    interface_exists: bool = True,
    interface_up: bool = True,
    listen_port: int | None = 45121,
    peer_count: int = 1,
) -> WireGuardHealth:
    return WireGuardHealth(
        interface_exists=interface_exists,
        interface_up=interface_up,
        listen_port=listen_port,
        peer_count=peer_count,
        latest_handshake=latest_handshake,
        rx_bytes=100,
        tx_bytes=200,
        status=WireGuardHealthStatus.UNKNOWN,
        reason=None,
        checked_at=datetime.now(timezone.utc),
    )


def make_policy(now: datetime) -> WireGuardHealthPolicy:
    return WireGuardHealthPolicy(
        now_provider=lambda: now,
    )


def test_fresh_handshake_is_healthy() -> None:
    now = datetime.now(timezone.utc)

    health = make_health(
        latest_handshake=now - timedelta(seconds=30),
    )

    result = make_policy(now).evaluate(health)

    assert result.status is WireGuardHealthStatus.HEALTHY
    assert result.reason is None


def test_stale_handshake_is_degraded() -> None:
    now = datetime.now(timezone.utc)

    health = make_health(
        latest_handshake=now - timedelta(seconds=120),
    )

    result = make_policy(now).evaluate(health)

    assert result.status is WireGuardHealthStatus.DEGRADED
    assert result.reason == "stale_handshake"


def test_expired_handshake_is_failed() -> None:
    now = datetime.now(timezone.utc)

    health = make_health(
        latest_handshake=now - timedelta(seconds=600),
    )

    result = make_policy(now).evaluate(health)

    assert result.status is WireGuardHealthStatus.FAILED
    assert result.reason == "handshake_timeout"


def test_handshake_at_90_seconds_is_healthy() -> None:
    now = datetime.now(timezone.utc)

    health = make_health(
        latest_handshake=now - timedelta(seconds=90),
    )

    result = make_policy(now).evaluate(health)

    assert result.status is WireGuardHealthStatus.HEALTHY


def test_handshake_at_91_seconds_is_degraded() -> None:
    now = datetime.now(timezone.utc)

    health = make_health(
        latest_handshake=now - timedelta(seconds=91),
    )

    result = make_policy(now).evaluate(health)

    assert result.status is WireGuardHealthStatus.DEGRADED


def test_handshake_at_300_seconds_is_degraded() -> None:
    now = datetime.now(timezone.utc)

    health = make_health(
        latest_handshake=now - timedelta(seconds=300),
    )

    result = make_policy(now).evaluate(health)

    assert result.status is WireGuardHealthStatus.DEGRADED


def test_handshake_at_301_seconds_is_failed() -> None:
    now = datetime.now(timezone.utc)

    health = make_health(
        latest_handshake=now - timedelta(seconds=301),
    )

    result = make_policy(now).evaluate(health)

    assert result.status is WireGuardHealthStatus.FAILED


def test_missing_interface_is_failed() -> None:
    health = make_health(
        latest_handshake=None,
        interface_exists=False,
    )

    now = datetime.now(timezone.utc)
    result = make_policy(now).evaluate(health)

    assert result.status is WireGuardHealthStatus.FAILED
    assert result.reason == "interface_not_found"


def test_interface_down_is_failed() -> None:
    health = make_health(
        latest_handshake=None,
        interface_up=False,
    )

    now = datetime.now(timezone.utc)
    result = make_policy(now).evaluate(health)

    assert result.status is WireGuardHealthStatus.FAILED
    assert result.reason == "interface_down"


def test_missing_listen_port_is_failed() -> None:
    health = make_health(
        latest_handshake=datetime.now(timezone.utc),
        listen_port=None,
    )

    now = datetime.now(timezone.utc)
    result = make_policy(now).evaluate(health)

    assert result.status is WireGuardHealthStatus.FAILED
    assert result.reason == "listen_port_unavailable"


def test_no_peers_is_degraded() -> None:
    health = make_health(
        latest_handshake=None,
        peer_count=0,
    )

    now = datetime.now(timezone.utc)
    result = make_policy(now).evaluate(health)

    assert result.status is WireGuardHealthStatus.DEGRADED
    assert result.reason == "no_peers"


def test_no_handshake_is_degraded() -> None:
    health = make_health(
        latest_handshake=None,
    )

    now = datetime.now(timezone.utc)
    result = make_policy(now).evaluate(health)

    assert result.status is WireGuardHealthStatus.DEGRADED
    assert result.reason == "no_handshake"
