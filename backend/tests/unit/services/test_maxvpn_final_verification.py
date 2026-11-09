from unittest.mock import Mock

from backend.models.maxvpn_installation import (
    InstallationPhase,
    InstallationStatus,
)
from backend.services.maxvpn_final_verification import (
    MaxVPNFinalVerificationService,
)


def make_wireguard_health(
    *,
    status: str,
    reason: str | None = None,
) -> Mock:
    health = Mock()
    health.status.value = status
    health.reason = reason
    return health


def make_firewall_verification(
    *,
    healthy: bool,
    reason: str | None = None,
) -> Mock:
    verification = Mock()
    verification.healthy = healthy
    verification.reason = reason
    return verification


def test_execute_returns_success_when_firewall_and_wireguard_are_healthy() -> None:
    firewall_verifier = Mock()
    firewall_verifier.verify.return_value = make_firewall_verification(
        healthy=True,
    )

    wireguard_health_check = Mock()
    wireguard_health_check.execute.return_value = make_wireguard_health(
        status="healthy",
    )

    service = MaxVPNFinalVerificationService(
        firewall_verifier=firewall_verifier,
        wireguard_health_check=wireguard_health_check,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.FINAL_VERIFY
    assert result.status == InstallationStatus.SUCCESS
    assert result.reason is None

    firewall_verifier.verify.assert_called_once_with()
    wireguard_health_check.execute.assert_called_once_with()


def test_execute_returns_failed_when_firewall_is_unhealthy() -> None:
    firewall_verifier = Mock()
    firewall_verifier.verify.return_value = make_firewall_verification(
        healthy=False,
        reason="firewall_verification_failed: ipv4_wan_drop",
    )

    wireguard_health_check = Mock()

    service = MaxVPNFinalVerificationService(
        firewall_verifier=firewall_verifier,
        wireguard_health_check=wireguard_health_check,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.FINAL_VERIFY
    assert result.status == InstallationStatus.FAILED
    assert result.reason == ("firewall_verification_failed: ipv4_wan_drop")

    firewall_verifier.verify.assert_called_once_with()
    wireguard_health_check.execute.assert_not_called()


def test_execute_returns_degraded_when_wireguard_is_degraded() -> None:
    firewall_verifier = Mock()
    firewall_verifier.verify.return_value = make_firewall_verification(
        healthy=True,
    )

    wireguard_health_check = Mock()
    wireguard_health_check.execute.return_value = make_wireguard_health(
        status="degraded",
        reason="stale_handshake",
    )

    service = MaxVPNFinalVerificationService(
        firewall_verifier=firewall_verifier,
        wireguard_health_check=wireguard_health_check,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.FINAL_VERIFY
    assert result.status == InstallationStatus.DEGRADED
    assert result.reason == "stale_handshake"


def test_execute_returns_failed_when_wireguard_is_failed() -> None:
    firewall_verifier = Mock()
    firewall_verifier.verify.return_value = make_firewall_verification(
        healthy=True,
    )

    wireguard_health_check = Mock()
    wireguard_health_check.execute.return_value = make_wireguard_health(
        status="failed",
        reason="peer_unreachable",
    )

    service = MaxVPNFinalVerificationService(
        firewall_verifier=firewall_verifier,
        wireguard_health_check=wireguard_health_check,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.FINAL_VERIFY
    assert result.status == InstallationStatus.FAILED
    assert result.reason == "peer_unreachable"


def test_execute_returns_failed_when_firewall_verifier_raises() -> None:
    firewall_verifier = Mock()
    firewall_verifier.verify.side_effect = RuntimeError(
        "ssh unavailable",
    )

    wireguard_health_check = Mock()

    service = MaxVPNFinalVerificationService(
        firewall_verifier=firewall_verifier,
        wireguard_health_check=wireguard_health_check,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.FINAL_VERIFY
    assert result.status == InstallationStatus.FAILED
    assert result.reason == ("firewall_final_verification_failed: ssh unavailable")


def test_execute_returns_failed_when_wireguard_health_check_raises() -> None:
    firewall_verifier = Mock()
    firewall_verifier.verify.return_value = make_firewall_verification(
        healthy=True,
    )

    wireguard_health_check = Mock()
    wireguard_health_check.execute.side_effect = RuntimeError(
        "health unavailable",
    )

    service = MaxVPNFinalVerificationService(
        firewall_verifier=firewall_verifier,
        wireguard_health_check=wireguard_health_check,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.FINAL_VERIFY
    assert result.status == InstallationStatus.FAILED
    assert result.reason == ("wireguard_final_verification_failed: health unavailable")
