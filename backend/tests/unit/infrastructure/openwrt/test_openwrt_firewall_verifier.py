from unittest.mock import Mock

from backend.infrastructure.openwrt.openwrt_firewall_verifier import (
    OpenWrtFirewallVerifier,
)
from backend.ports.remote_command_executor import RemoteCommandExecutor


def make_result(
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> Mock:
    return Mock(
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
    )


def configure_healthy_executor() -> Mock:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        make_result(
            stdout=(
                "-N MAXVPN_LAN_FORWARD\n"
                "-A MAXVPN_LAN_FORWARD -i br-lan "
                "-o WireGuard -j ACCEPT\n"
                "-A MAXVPN_LAN_FORWARD -i br-lan "
                "-o eth1 -j DROP\n"
                "-A MAXVPN_LAN_FORWARD -j RETURN\n"
            )
        ),
        make_result(
            stdout=("-N forwarding_rule\n-A forwarding_rule -j MAXVPN_LAN_FORWARD\n")
        ),
        make_result(
            stdout=(
                "-N MAXVPN_LAN6_FORWARD\n"
                "-A MAXVPN_LAN6_FORWARD -i br-lan "
                "-o WireGuard -j ACCEPT\n"
                "-A MAXVPN_LAN6_FORWARD -i br-lan "
                "-o eth1 -j DROP\n"
                "-A MAXVPN_LAN6_FORWARD -j RETURN\n"
            )
        ),
        make_result(
            stdout=("-N forwarding_rule\n-A forwarding_rule -j MAXVPN_LAN6_FORWARD\n")
        ),
    ]

    return executor


def test_verify_returns_healthy_for_valid_firewall() -> None:
    executor = configure_healthy_executor()

    verifier = OpenWrtFirewallVerifier(
        executor=executor,
    )

    result = verifier.verify()

    assert result.healthy is True
    assert result.reason is None

    assert result.ipv4_chain_exists is True
    assert result.ipv6_chain_exists is True

    assert result.ipv4_jump_count == 1
    assert result.ipv6_jump_count == 1

    assert result.ipv4_vpn_accept_rule is True
    assert result.ipv4_wan_drop_rule is True

    assert result.ipv6_vpn_accept_rule is True
    assert result.ipv6_wan_drop_rule is True

    assert executor.run.call_count == 4


def test_verify_fails_when_ipv4_chain_is_missing() -> None:
    executor = configure_healthy_executor()

    executor.run.side_effect = [
        make_result(
            returncode=1,
            stderr="iptables: No chain/target/match by that name.",
        ),
        make_result(
            stdout="-N forwarding_rule\n-A forwarding_rule -j MAXVPN_LAN_FORWARD\n"
        ),
        make_result(
            stdout=(
                "-N MAXVPN_LAN6_FORWARD\n"
                "-A MAXVPN_LAN6_FORWARD -i br-lan "
                "-o WireGuard -j ACCEPT\n"
                "-A MAXVPN_LAN6_FORWARD -i br-lan "
                "-o eth1 -j DROP\n"
                "-A MAXVPN_LAN6_FORWARD -j RETURN\n"
            )
        ),
        make_result(
            stdout=("-N forwarding_rule\n-A forwarding_rule -j MAXVPN_LAN6_FORWARD\n")
        ),
    ]

    verifier = OpenWrtFirewallVerifier(
        executor=executor,
    )

    result = verifier.verify()

    assert result.healthy is False
    assert result.ipv4_chain_exists is False
    assert result.reason is not None
    assert "ipv4_chain_exists" in result.reason


def test_verify_fails_when_ipv4_jump_is_duplicated() -> None:
    executor = configure_healthy_executor()

    executor.run.side_effect = [
        make_result(
            stdout=(
                "-N MAXVPN_LAN_FORWARD\n"
                "-A MAXVPN_LAN_FORWARD -i br-lan "
                "-o WireGuard -j ACCEPT\n"
                "-A MAXVPN_LAN_FORWARD -i br-lan "
                "-o eth1 -j DROP\n"
                "-A MAXVPN_LAN_FORWARD -j RETURN\n"
            )
        ),
        make_result(
            stdout=(
                "-N forwarding_rule\n"
                "-A forwarding_rule -j MAXVPN_LAN_FORWARD\n"
                "-A forwarding_rule -j MAXVPN_LAN_FORWARD\n"
            )
        ),
        make_result(
            stdout=(
                "-N MAXVPN_LAN6_FORWARD\n"
                "-A MAXVPN_LAN6_FORWARD -i br-lan "
                "-o WireGuard -j ACCEPT\n"
                "-A MAXVPN_LAN6_FORWARD -i br-lan "
                "-o eth1 -j DROP\n"
                "-A MAXVPN_LAN6_FORWARD -j RETURN\n"
            )
        ),
        make_result(
            stdout=("-N forwarding_rule\n-A forwarding_rule -j MAXVPN_LAN6_FORWARD\n")
        ),
    ]

    verifier = OpenWrtFirewallVerifier(
        executor=executor,
    )

    result = verifier.verify()

    assert result.healthy is False
    assert result.ipv4_jump_count == 2
    assert result.reason is not None
    assert "ipv4_single_jump" in result.reason


def test_verify_fails_when_ipv4_wan_drop_is_missing() -> None:
    executor = configure_healthy_executor()

    executor.run.side_effect = [
        make_result(
            stdout=(
                "-N MAXVPN_LAN_FORWARD\n"
                "-A MAXVPN_LAN_FORWARD -i br-lan "
                "-o WireGuard -j ACCEPT\n"
                "-A MAXVPN_LAN_FORWARD -j RETURN\n"
            )
        ),
        make_result(
            stdout=("-N forwarding_rule\n-A forwarding_rule -j MAXVPN_LAN_FORWARD\n")
        ),
        make_result(
            stdout=(
                "-N MAXVPN_LAN6_FORWARD\n"
                "-A MAXVPN_LAN6_FORWARD -i br-lan "
                "-o WireGuard -j ACCEPT\n"
                "-A MAXVPN_LAN6_FORWARD -i br-lan "
                "-o eth1 -j DROP\n"
                "-A MAXVPN_LAN6_FORWARD -j RETURN\n"
            )
        ),
        make_result(
            stdout=("-N forwarding_rule\n-A forwarding_rule -j MAXVPN_LAN6_FORWARD\n")
        ),
    ]

    verifier = OpenWrtFirewallVerifier(
        executor=executor,
    )

    result = verifier.verify()

    assert result.healthy is False
    assert result.ipv4_wan_drop_rule is False
    assert result.reason is not None
    assert "ipv4_wan_drop" in result.reason


def test_verify_fails_when_ipv6_jump_is_missing() -> None:
    executor = configure_healthy_executor()

    executor.run.side_effect = [
        make_result(
            stdout=(
                "-N MAXVPN_LAN_FORWARD\n"
                "-A MAXVPN_LAN_FORWARD -i br-lan "
                "-o WireGuard -j ACCEPT\n"
                "-A MAXVPN_LAN_FORWARD -i br-lan "
                "-o eth1 -j DROP\n"
                "-A MAXVPN_LAN_FORWARD -j RETURN\n"
            )
        ),
        make_result(
            stdout=("-N forwarding_rule\n-A forwarding_rule -j MAXVPN_LAN_FORWARD\n")
        ),
        make_result(
            stdout=(
                "-N MAXVPN_LAN6_FORWARD\n"
                "-A MAXVPN_LAN6_FORWARD -i br-lan "
                "-o WireGuard -j ACCEPT\n"
                "-A MAXVPN_LAN6_FORWARD -i br-lan "
                "-o eth1 -j DROP\n"
                "-A MAXVPN_LAN6_FORWARD -j RETURN\n"
            )
        ),
        make_result(
            stdout="-N forwarding_rule\n",
        ),
    ]

    verifier = OpenWrtFirewallVerifier(
        executor=executor,
    )

    result = verifier.verify()

    assert result.healthy is False
    assert result.ipv6_jump_count == 0
    assert result.reason is not None
    assert "ipv6_single_jump" in result.reason


def test_verify_fails_when_ipv6_vpn_accept_is_missing() -> None:
    executor = configure_healthy_executor()

    executor.run.side_effect = [
        make_result(
            stdout=(
                "-N MAXVPN_LAN_FORWARD\n"
                "-A MAXVPN_LAN_FORWARD -i br-lan "
                "-o WireGuard -j ACCEPT\n"
                "-A MAXVPN_LAN_FORWARD -i br-lan "
                "-o eth1 -j DROP\n"
                "-A MAXVPN_LAN_FORWARD -j RETURN\n"
            )
        ),
        make_result(
            stdout=("-N forwarding_rule\n-A forwarding_rule -j MAXVPN_LAN_FORWARD\n")
        ),
        make_result(
            stdout=(
                "-N MAXVPN_LAN6_FORWARD\n"
                "-A MAXVPN_LAN6_FORWARD -i br-lan "
                "-o eth1 -j DROP\n"
                "-A MAXVPN_LAN6_FORWARD -j RETURN\n"
            )
        ),
        make_result(
            stdout=("-N forwarding_rule\n-A forwarding_rule -j MAXVPN_LAN6_FORWARD\n")
        ),
    ]

    verifier = OpenWrtFirewallVerifier(
        executor=executor,
    )

    result = verifier.verify()

    assert result.healthy is False
    assert result.ipv6_vpn_accept_rule is False
    assert result.reason is not None
    assert "ipv6_vpn_accept" in result.reason


def test_verify_detects_multiple_failures() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        make_result(returncode=1, stderr="missing"),
        make_result(stdout="-N forwarding_rule\n"),
        make_result(returncode=1, stderr="missing"),
        make_result(stdout="-N forwarding_rule\n"),
    ]

    verifier = OpenWrtFirewallVerifier(
        executor=executor,
    )

    result = verifier.verify()

    assert result.healthy is False
    assert result.reason is not None
    assert "ipv4_chain_exists" in result.reason
    assert "ipv6_chain_exists" in result.reason
