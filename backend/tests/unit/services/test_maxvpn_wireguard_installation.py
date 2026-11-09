from unittest.mock import Mock

from backend.models.maxvpn_installation import (
    InstallationPhase,
    InstallationStatus,
)
from backend.services.maxvpn_wireguard_installation import (
    MaxVPNWireGuardInstallationService,
)


def make_health(
    *,
    status: str = "healthy",
    reason: str | None = None,
    interface_exists: bool = True,
    interface_up: bool = True,
) -> Mock:
    health = Mock()
    health.status.value = status
    health.reason = reason
    health.interface_exists = interface_exists
    health.interface_up = interface_up
    return health


def test_execute_returns_success_for_healthy_wireguard() -> None:
    health_check = Mock()
    health_check.execute.return_value = make_health()

    service = MaxVPNWireGuardInstallationService(
        health_check=health_check,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.WIREGUARD
    assert result.status == InstallationStatus.SUCCESS
    assert result.reason is None

    health_check.execute.assert_called_once_with()


def test_execute_rechecks_degraded_state_and_recovers() -> None:
    health_check = Mock()
    health_check.execute.side_effect = [
        make_health(
            status="degraded",
            reason="stale_handshake",
        ),
        make_health(
            status="healthy",
        ),
    ]

    service = MaxVPNWireGuardInstallationService(
        health_check=health_check,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.WIREGUARD
    assert result.status == InstallationStatus.SUCCESS
    assert result.reason is None
    assert health_check.execute.call_count == 2


def test_execute_returns_degraded_when_recheck_stays_degraded() -> None:
    health_check = Mock()
    health_check.execute.side_effect = [
        make_health(
            status="degraded",
            reason="stale_handshake",
        ),
        make_health(
            status="degraded",
            reason="stale_handshake",
        ),
    ]

    service = MaxVPNWireGuardInstallationService(
        health_check=health_check,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.WIREGUARD
    assert result.status == InstallationStatus.DEGRADED
    assert result.reason == "stale_handshake"
    assert health_check.execute.call_count == 2


def test_execute_fails_when_interface_is_missing() -> None:
    health_check = Mock()
    health_check.execute.return_value = make_health(
        interface_exists=False,
        interface_up=False,
    )

    service = MaxVPNWireGuardInstallationService(
        health_check=health_check,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.WIREGUARD
    assert result.status == InstallationStatus.FAILED
    assert result.reason == "wireguard_interface_missing"


def test_execute_fails_when_interface_is_down() -> None:
    health_check = Mock()
    health_check.execute.return_value = make_health(
        interface_exists=True,
        interface_up=False,
    )

    service = MaxVPNWireGuardInstallationService(
        health_check=health_check,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.WIREGUARD
    assert result.status == InstallationStatus.FAILED
    assert result.reason == "wireguard_interface_down"


def test_execute_fails_when_health_check_raises() -> None:
    health_check = Mock()
    health_check.execute.side_effect = RuntimeError("health unavailable")

    service = MaxVPNWireGuardInstallationService(
        health_check=health_check,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.WIREGUARD
    assert result.status == InstallationStatus.FAILED
    assert result.reason is not None
    assert "health unavailable" in result.reason
