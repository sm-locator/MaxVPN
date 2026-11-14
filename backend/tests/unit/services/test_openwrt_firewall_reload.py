from unittest.mock import Mock

from backend.infrastructure.openwrt.openwrt_firewall_verifier import (
    OpenWrtFirewallVerificationResult,
)
from backend.ports.remote_command_executor import RemoteCommandExecutor
from backend.services.openwrt_firewall_reload import (
    OpenWrtFirewallReloadService,
)


def healthy_verification() -> OpenWrtFirewallVerificationResult:
    return OpenWrtFirewallVerificationResult(
        healthy=True,
        ipv4_chain_exists=True,
        ipv6_chain_exists=True,
        ipv4_jump_count=1,
        ipv6_jump_count=1,
        ipv4_vpn_accept_rule=True,
        ipv4_wan_drop_rule=True,
        ipv6_vpn_accept_rule=True,
        ipv6_wan_drop_rule=True,
        reason=None,
    )


def failed_verification() -> OpenWrtFirewallVerificationResult:
    return OpenWrtFirewallVerificationResult(
        healthy=False,
        ipv4_chain_exists=False,
        ipv6_chain_exists=True,
        ipv4_jump_count=0,
        ipv6_jump_count=1,
        ipv4_vpn_accept_rule=False,
        ipv4_wan_drop_rule=False,
        ipv6_vpn_accept_rule=True,
        ipv6_wan_drop_rule=True,
        reason="firewall_verification_failed: ipv4_chain_exists",
    )


def test_reload_success_when_fw3_and_verifier_succeed() -> None:
    executor = Mock(spec=RemoteCommandExecutor)
    executor.run.return_value = Mock(
        returncode=0,
        stdout="",
        stderr="",
    )

    verifier = Mock()
    verifier.verify.return_value = healthy_verification()

    service = OpenWrtFirewallReloadService(
        executor=executor,
        verifier=verifier,
    )

    result = service.reload()

    assert result.reload_returncode == 0
    assert result.reload_succeeded is True
    assert result.healthy is True
    assert result.degraded is False
    assert result.reason is None

    executor.run.assert_called_once_with(
        [
            "fw3",
            "reload",
        ]
    )

    verifier.verify.assert_called_once_with()


def test_reload_is_healthy_when_fw3_fails_but_maxvpn_state_is_valid() -> None:
    executor = Mock(spec=RemoteCommandExecutor)
    executor.run.return_value = Mock(
        returncode=1,
        stdout="",
        stderr="pre-existing firewall component failed",
    )

    verifier = Mock()
    verifier.verify.return_value = healthy_verification()

    service = OpenWrtFirewallReloadService(
        executor=executor,
        verifier=verifier,
    )

    result = service.reload()

    assert result.reload_returncode == 1
    assert result.reload_succeeded is False
    assert result.healthy is True
    assert result.degraded is True
    assert result.reason == "fw3_reload_returned_nonzero_but_maxvpn_firewall_is_healthy"


def test_reload_fails_when_fw3_succeeds_but_maxvpn_state_is_invalid() -> None:
    executor = Mock(spec=RemoteCommandExecutor)
    executor.run.return_value = Mock(
        returncode=0,
        stdout="",
        stderr="",
    )

    verifier = Mock()
    verifier.verify.return_value = failed_verification()

    service = OpenWrtFirewallReloadService(
        executor=executor,
        verifier=verifier,
    )

    result = service.reload()

    assert result.reload_returncode == 0
    assert result.reload_succeeded is True
    assert result.healthy is False
    assert result.degraded is False
    assert result.reason == "firewall_verification_failed: ipv4_chain_exists"


def test_reload_fails_when_fw3_and_maxvpn_state_fail() -> None:
    executor = Mock(spec=RemoteCommandExecutor)
    executor.run.return_value = Mock(
        returncode=1,
        stdout="",
        stderr="fw3 failed",
    )

    verifier = Mock()
    verifier.verify.return_value = failed_verification()

    service = OpenWrtFirewallReloadService(
        executor=executor,
        verifier=verifier,
    )

    result = service.reload()

    assert result.reload_returncode == 1
    assert result.reload_succeeded is False
    assert result.healthy is False
    assert result.degraded is False
    assert result.reason == "firewall_verification_failed: ipv4_chain_exists"


def test_reload_always_verifies_runtime_state() -> None:
    executor = Mock(spec=RemoteCommandExecutor)
    executor.run.return_value = Mock(
        returncode=1,
        stdout="",
        stderr="fw3 failed",
    )

    verifier = Mock()
    verifier.verify.return_value = healthy_verification()

    service = OpenWrtFirewallReloadService(
        executor=executor,
        verifier=verifier,
    )

    service.reload()

    verifier.verify.assert_called_once_with()


def test_degraded_property_is_true_only_for_nonzero_reload_with_healthy_state() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    verifier = Mock()
    verifier.verify.return_value = healthy_verification()

    executor.run.return_value = Mock(
        returncode=1,
        stdout="",
        stderr="",
    )

    service = OpenWrtFirewallReloadService(
        executor=executor,
        verifier=verifier,
    )

    result = service.reload()

    assert result.degraded is True


def test_degraded_property_is_false_for_clean_success() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    verifier = Mock()
    verifier.verify.return_value = healthy_verification()

    executor.run.return_value = Mock(
        returncode=0,
        stdout="",
        stderr="",
    )

    service = OpenWrtFirewallReloadService(
        executor=executor,
        verifier=verifier,
    )

    result = service.reload()

    assert result.degraded is False
