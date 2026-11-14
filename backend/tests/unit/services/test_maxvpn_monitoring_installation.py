from unittest.mock import Mock

from backend.models.maxvpn_installation import (
    InstallationPhase,
    InstallationStatus,
)
from backend.models.wireguard_health import WireGuardHealthStatus
from backend.services.maxvpn_monitoring_installation import (
    MaxVPNMonitoringInstallationService,
)


def make_health(
    *,
    status: WireGuardHealthStatus,
    reason: str | None = None,
) -> Mock:
    health = Mock()
    health.status = status
    health.reason = reason
    return health


def make_result(
    *,
    health: Mock,
    recovered: bool = False,
) -> Mock:
    result = Mock()
    result.monitoring.health = health

    if recovered:
        result.recovery = Mock()
        result.recovery.recovered = True
    else:
        result.recovery = None

    return result


def test_execute_returns_success_for_healthy_monitoring() -> None:
    monitor_and_recover = Mock()
    monitor_and_recover.execute.return_value = make_result(
        health=make_health(
            status=WireGuardHealthStatus.HEALTHY,
        ),
    )

    service = MaxVPNMonitoringInstallationService(
        monitor_and_recover=monitor_and_recover,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.MONITORING
    assert result.status == InstallationStatus.SUCCESS
    assert result.reason is None

    monitor_and_recover.execute.assert_called_once_with()


def test_execute_returns_success_when_recovery_recovers_wireguard() -> None:
    monitor_and_recover = Mock()
    monitor_and_recover.execute.return_value = make_result(
        health=make_health(
            status=WireGuardHealthStatus.FAILED,
            reason="interface_failed",
        ),
        recovered=True,
    )

    service = MaxVPNMonitoringInstallationService(
        monitor_and_recover=monitor_and_recover,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.MONITORING
    assert result.status == InstallationStatus.SUCCESS
    assert result.reason is None


def test_execute_returns_degraded_for_degraded_monitoring() -> None:
    monitor_and_recover = Mock()
    monitor_and_recover.execute.return_value = make_result(
        health=make_health(
            status=WireGuardHealthStatus.DEGRADED,
            reason="stale_handshake",
        ),
    )

    service = MaxVPNMonitoringInstallationService(
        monitor_and_recover=monitor_and_recover,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.MONITORING
    assert result.status == InstallationStatus.DEGRADED
    assert result.reason == "stale_handshake"


def test_execute_returns_failed_for_failed_monitoring() -> None:
    monitor_and_recover = Mock()
    monitor_and_recover.execute.return_value = make_result(
        health=make_health(
            status=WireGuardHealthStatus.FAILED,
            reason="peer_unreachable",
        ),
    )

    service = MaxVPNMonitoringInstallationService(
        monitor_and_recover=monitor_and_recover,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.MONITORING
    assert result.status == InstallationStatus.FAILED
    assert result.reason == "peer_unreachable"


def test_execute_returns_failed_when_monitoring_raises() -> None:
    monitor_and_recover = Mock()
    monitor_and_recover.execute.side_effect = RuntimeError(
        "monitoring unavailable",
    )

    service = MaxVPNMonitoringInstallationService(
        monitor_and_recover=monitor_and_recover,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.MONITORING
    assert result.status == InstallationStatus.FAILED
    assert result.reason is not None
    assert "monitoring unavailable" in result.reason
