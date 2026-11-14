from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from backend.application.use_cases.check_wireguard_health import (
    CheckWireGuardHealthUseCase,
)
from backend.application.use_cases.monitor_wireguard import (
    MonitorWireGuardUseCase,
)
from backend.models.wireguard_health import (
    WireGuardHealth,
    WireGuardHealthStatus,
)
from backend.models.wireguard_monitoring_result import WireGuardMonitoringResult
from backend.services.wireguard_monitor import WireGuardMonitor


def make_health(
    status: WireGuardHealthStatus,
    checked_at: datetime,
) -> WireGuardHealth:
    return WireGuardHealth(
        interface_exists=True,
        interface_up=True,
        listen_port=45121,
        peer_count=1,
        latest_handshake=checked_at,
        rx_bytes=100,
        tx_bytes=200,
        status=status,
        reason=None,
        checked_at=checked_at,
    )


def test_execute_returns_healthy_monitoring_result() -> None:
    checked_at = datetime.now(timezone.utc)

    health = make_health(
        WireGuardHealthStatus.HEALTHY,
        checked_at,
    )

    health_check = Mock(spec=CheckWireGuardHealthUseCase)
    health_check.execute.return_value = health

    monitor = WireGuardMonitor()

    use_case = MonitorWireGuardUseCase(
        health_check=health_check,
        monitor=monitor,
    )

    result = use_case.execute()

    assert isinstance(result, WireGuardMonitoringResult)
    assert result.health is health
    assert result.state.status is WireGuardHealthStatus.HEALTHY
    assert result.recovery_required is False

    health_check.execute.assert_called_once_with()


def test_execute_marks_recovery_required_after_three_degraded_checks() -> None:
    start = datetime.now(timezone.utc)

    health_check = Mock(spec=CheckWireGuardHealthUseCase)
    health_check.execute.side_effect = [
        make_health(
            WireGuardHealthStatus.DEGRADED,
            start,
        ),
        make_health(
            WireGuardHealthStatus.DEGRADED,
            start + timedelta(seconds=10),
        ),
        make_health(
            WireGuardHealthStatus.DEGRADED,
            start + timedelta(seconds=20),
        ),
    ]

    monitor = WireGuardMonitor()

    use_case = MonitorWireGuardUseCase(
        health_check=health_check,
        monitor=monitor,
    )

    first = use_case.execute()
    second = use_case.execute()
    third = use_case.execute()

    assert first.state.status is WireGuardHealthStatus.DEGRADED
    assert first.recovery_required is False

    assert second.state.status is WireGuardHealthStatus.DEGRADED
    assert second.recovery_required is False

    assert third.state.status is WireGuardHealthStatus.FAILED
    assert third.recovery_required is True

    assert health_check.execute.call_count == 3


def test_execute_clears_recovery_after_healthy_check() -> None:
    start = datetime.now(timezone.utc)

    health_check = Mock(spec=CheckWireGuardHealthUseCase)
    health_check.execute.side_effect = [
        make_health(
            WireGuardHealthStatus.FAILED,
            start,
        ),
        make_health(
            WireGuardHealthStatus.HEALTHY,
            start + timedelta(seconds=10),
        ),
    ]

    monitor = WireGuardMonitor()

    use_case = MonitorWireGuardUseCase(
        health_check=health_check,
        monitor=monitor,
    )

    failed = use_case.execute()
    recovered = use_case.execute()

    assert failed.state.status is WireGuardHealthStatus.FAILED
    assert failed.recovery_required is True

    assert recovered.state.status is WireGuardHealthStatus.HEALTHY
    assert recovered.recovery_required is False


def test_execute_preserves_health_payload() -> None:
    checked_at = datetime.now(timezone.utc)

    health = make_health(
        WireGuardHealthStatus.DEGRADED,
        checked_at,
    )

    health_check = Mock(spec=CheckWireGuardHealthUseCase)
    health_check.execute.return_value = health

    monitor = WireGuardMonitor()

    use_case = MonitorWireGuardUseCase(
        health_check=health_check,
        monitor=monitor,
    )

    result = use_case.execute()

    assert result.health.interface_exists is True
    assert result.health.interface_up is True
    assert result.health.listen_port == 45121
    assert result.health.peer_count == 1
    assert result.health.latest_handshake == checked_at
    assert result.health.rx_bytes == 100
    assert result.health.tx_bytes == 200
