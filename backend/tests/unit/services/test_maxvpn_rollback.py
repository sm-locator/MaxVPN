from unittest.mock import Mock

from backend.models.maxvpn_installation import (
    InstallationPhase,
    InstallationStatus,
)
from backend.services.maxvpn_rollback import MaxVPNRollbackService


def test_execute_returns_success_when_persistence_uninstalls() -> None:
    persistence = Mock()

    service = MaxVPNRollbackService(
        persistence=persistence,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.ROLLBACK
    assert result.status == InstallationStatus.SUCCESS
    assert result.reason is None

    persistence.uninstall.assert_called_once_with()


def test_execute_returns_failure_when_persistence_uninstall_raises() -> None:
    persistence = Mock()
    persistence.uninstall.side_effect = RuntimeError(
        "permission denied",
    )

    service = MaxVPNRollbackService(
        persistence=persistence,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.ROLLBACK
    assert result.status == InstallationStatus.FAILED
    assert result.reason is not None
    assert "permission denied" in result.reason

    persistence.uninstall.assert_called_once_with()


def test_execute_preserves_existing_rollback_error() -> None:
    persistence = Mock()
    persistence.uninstall.side_effect = RuntimeError(
        "firewall.user is corrupted",
    )

    service = MaxVPNRollbackService(
        persistence=persistence,
    )

    result = service.execute()

    assert result.status == InstallationStatus.FAILED
    assert result.reason == ("firewall_rollback_failed: firewall.user is corrupted")


def test_execute_does_not_require_vpn_policy() -> None:
    persistence = Mock()

    service = MaxVPNRollbackService(
        persistence=persistence,
    )

    result = service.execute()

    assert result.status == InstallationStatus.SUCCESS
