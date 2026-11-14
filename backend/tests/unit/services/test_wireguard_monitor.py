from datetime import datetime, timedelta, timezone

from backend.models.wireguard_health import WireGuardHealthStatus
from backend.services.wireguard_monitor import (
    WireGuardMonitor,
    WireGuardMonitorThresholds,
)


def test_first_healthy_check_creates_healthy_state() -> None:
    now = datetime.now(timezone.utc)

    monitor = WireGuardMonitor()

    state = monitor.update(
        WireGuardHealthStatus.HEALTHY,
        checked_at=now,
    )

    assert state.status is WireGuardHealthStatus.HEALTHY
    assert state.consecutive_failures == 0
    assert state.consecutive_degraded == 0
    assert state.last_status_change == now
    assert state.last_check_at == now


def test_three_degraded_checks_transition_to_failed() -> None:
    now = datetime.now(timezone.utc)

    monitor = WireGuardMonitor(
        thresholds=WireGuardMonitorThresholds(
            degraded_to_failed_checks=3,
        )
    )

    state1 = monitor.update(
        WireGuardHealthStatus.DEGRADED,
        checked_at=now,
    )
    state2 = monitor.update(
        WireGuardHealthStatus.DEGRADED,
        checked_at=now + timedelta(seconds=10),
    )
    state3 = monitor.update(
        WireGuardHealthStatus.DEGRADED,
        checked_at=now + timedelta(seconds=20),
    )

    assert state1.status is WireGuardHealthStatus.DEGRADED
    assert state2.status is WireGuardHealthStatus.DEGRADED
    assert state3.status is WireGuardHealthStatus.FAILED

    assert state3.consecutive_degraded == 3


def test_healthy_check_resets_failure_counters() -> None:
    now = datetime.now(timezone.utc)

    monitor = WireGuardMonitor()

    monitor.update(
        WireGuardHealthStatus.FAILED,
        checked_at=now,
    )

    state = monitor.update(
        WireGuardHealthStatus.HEALTHY,
        checked_at=now + timedelta(seconds=10),
    )

    assert state.status is WireGuardHealthStatus.HEALTHY
    assert state.consecutive_failures == 0
    assert state.consecutive_degraded == 0


def test_status_change_updates_last_status_change() -> None:
    now = datetime.now(timezone.utc)

    monitor = WireGuardMonitor()

    first = monitor.update(
        WireGuardHealthStatus.HEALTHY,
        checked_at=now,
    )

    second = monitor.update(
        WireGuardHealthStatus.DEGRADED,
        checked_at=now + timedelta(seconds=10),
    )

    assert first.last_status_change == now
    assert second.last_status_change == now + timedelta(seconds=10)


def test_same_status_keeps_original_status_change_time() -> None:
    now = datetime.now(timezone.utc)

    monitor = WireGuardMonitor()

    first = monitor.update(
        WireGuardHealthStatus.DEGRADED,
        checked_at=now,
    )

    second = monitor.update(
        WireGuardHealthStatus.DEGRADED,
        checked_at=now + timedelta(seconds=10),
    )

    assert second.last_status_change == first.last_status_change


def test_reset_clears_monitor_state() -> None:
    monitor = WireGuardMonitor()

    monitor.update(WireGuardHealthStatus.HEALTHY)

    monitor.reset()

    assert monitor.state is None
