from unittest.mock import Mock

from backend.models.maxvpn_installation import (
    InstallationPhase,
    InstallationStatus,
)
from backend.models.vpn_traffic_policy import VpnTrafficPolicy
from backend.services.maxvpn_firewall_installation import (
    MaxVPNFirewallInstallationService,
)


def make_policy() -> VpnTrafficPolicy:
    return VpnTrafficPolicy(
        lan_interface="br-lan",
        vpn_interface="WireGuard",
        wan_interface="eth1",
        allow_lan_to_vpn=True,
        allow_lan_to_wan=False,
        allow_lan_to_wan_ipv6=False,
        allow_vpn_endpoint_via_wan=True,
    )


def test_execute_returns_success_when_persistence_succeeds() -> None:
    persistence = Mock()
    persistence.install.return_value = None

    policy = make_policy()

    service = MaxVPNFirewallInstallationService(
        persistence=persistence,
        policy=policy,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.FIREWALL
    assert result.status == InstallationStatus.SUCCESS
    assert result.reason is None

    persistence.install.assert_called_once_with(policy)


def test_execute_returns_degraded_when_reload_is_degraded() -> None:
    persistence = Mock()

    reload_result = Mock()
    reload_result.degraded = True
    reload_result.reason = "fw3_reload_returned_nonzero_but_maxvpn_firewall_is_healthy"

    persistence.install.return_value = reload_result

    policy = make_policy()

    service = MaxVPNFirewallInstallationService(
        persistence=persistence,
        policy=policy,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.FIREWALL
    assert result.status == InstallationStatus.DEGRADED
    assert result.reason == "fw3_reload_returned_nonzero_but_maxvpn_firewall_is_healthy"

    persistence.install.assert_called_once_with(policy)


def test_execute_returns_failure_when_persistence_raises() -> None:
    persistence = Mock()
    persistence.install.side_effect = RuntimeError("permission denied")

    policy = make_policy()

    service = MaxVPNFirewallInstallationService(
        persistence=persistence,
        policy=policy,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.FIREWALL
    assert result.status == InstallationStatus.FAILED
    assert result.reason is not None
    assert "permission denied" in result.reason

    persistence.install.assert_called_once_with(policy)


def test_execute_accepts_persistence_without_reload_result() -> None:
    persistence = Mock()
    persistence.install.return_value = None

    policy = make_policy()

    service = MaxVPNFirewallInstallationService(
        persistence=persistence,
        policy=policy,
    )

    result = service.execute()

    assert result.phase == InstallationPhase.FIREWALL
    assert result.status == InstallationStatus.SUCCESS
    assert result.reason is None

    persistence.install.assert_called_once_with(policy)
