from datetime import datetime, timedelta, timezone

from backend.models.amneziawg_runtime_health import (
    AmneziaWGRuntimeHealth,
)
from backend.services.amneziawg_runtime_health_policy import (
    AmneziaWGRuntimeHealthPolicy,
)


def make_health(handshake: datetime) -> AmneziaWGRuntimeHealth:
    return AmneziaWGRuntimeHealth(
        interface_exists=True,
        interface_up=True,
        expected_peer_found=True,
        expected_endpoint=True,
        listen_port=43095,
        latest_handshake=handshake,
        rx_bytes=1000,
        tx_bytes=1000,
        endpoint_route_ok=True,
        healthy=True,
        reason=None,
        checked_at=handshake,
    )


def test_recent_handshake_is_healthy():
    now = datetime(
        2026,
        8,
        21,
        20,
        0,
        0,
        tzinfo=timezone.utc,
    )

    policy = AmneziaWGRuntimeHealthPolicy(
        now_provider=lambda: now,
    )

    result = policy.evaluate(make_health(now - timedelta(seconds=30)))

    assert result.healthy is True
    assert result.reason is None


def test_stale_handshake_does_not_mark_runtime_unhealthy():
    now = datetime(
        2026,
        8,
        21,
        20,
        0,
        0,
        tzinfo=timezone.utc,
    )

    policy = AmneziaWGRuntimeHealthPolicy(
        now_provider=lambda: now,
    )

    result = policy.evaluate(make_health(now - timedelta(seconds=120)))

    assert result.healthy is True
    assert result.reason is None


def test_old_handshake_is_timeout():
    now = datetime(
        2026,
        8,
        21,
        20,
        0,
        0,
        tzinfo=timezone.utc,
    )

    policy = AmneziaWGRuntimeHealthPolicy(
        now_provider=lambda: now,
    )

    result = policy.evaluate(make_health(now - timedelta(seconds=600)))

    assert result.healthy is False
    assert result.reason == "handshake_timeout"
