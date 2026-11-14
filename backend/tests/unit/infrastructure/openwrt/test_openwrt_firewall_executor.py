from unittest.mock import Mock

from backend.infrastructure.openwrt.openwrt_firewall_executor import (
    OpenWrtFirewallExecutor,
)
from backend.models.vpn_traffic_policy import VpnTrafficPolicy
from backend.ports.remote_command_executor import RemoteCommandExecutor


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


def test_build_commands_contains_ipv4_fail_closed_rules() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    firewall = OpenWrtFirewallExecutor(
        executor=executor,
    )

    commands = firewall.build_commands(make_policy())

    assert [
        "iptables",
        "-A",
        "MAXVPN_LAN_FORWARD",
        "-i",
        "br-lan",
        "-o",
        "WireGuard",
        "-j",
        "ACCEPT",
    ] in commands

    assert [
        "iptables",
        "-A",
        "MAXVPN_LAN_FORWARD",
        "-i",
        "br-lan",
        "-o",
        "eth1",
        "-j",
        "DROP",
    ] in commands


def test_build_commands_contains_ipv6_fail_closed_rules() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    firewall = OpenWrtFirewallExecutor(
        executor=executor,
    )

    commands = firewall.build_commands(make_policy())

    assert [
        "ip6tables",
        "-A",
        "MAXVPN_LAN6_FORWARD",
        "-i",
        "br-lan",
        "-o",
        "WireGuard",
        "-j",
        "ACCEPT",
    ] in commands

    assert [
        "ip6tables",
        "-A",
        "MAXVPN_LAN6_FORWARD",
        "-i",
        "br-lan",
        "-o",
        "eth1",
        "-j",
        "DROP",
    ] in commands


def test_build_commands_inserts_ipv4_chain_into_forwarding_rule() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    firewall = OpenWrtFirewallExecutor(
        executor=executor,
    )

    commands = firewall.build_commands(make_policy())

    assert [
        "iptables",
        "-D",
        "forwarding_rule",
        "-j",
        "MAXVPN_LAN_FORWARD",
    ] in commands

    assert [
        "iptables",
        "-I",
        "forwarding_rule",
        "1",
        "-j",
        "MAXVPN_LAN_FORWARD",
    ] in commands


def test_build_commands_inserts_ipv6_chain_into_forwarding_rule() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    firewall = OpenWrtFirewallExecutor(
        executor=executor,
    )

    commands = firewall.build_commands(make_policy())

    assert [
        "ip6tables",
        "-D",
        "forwarding_rule",
        "-j",
        "MAXVPN_LAN6_FORWARD",
    ] in commands

    assert [
        "ip6tables",
        "-I",
        "forwarding_rule",
        "1",
        "-j",
        "MAXVPN_LAN6_FORWARD",
    ] in commands


def test_build_commands_only_does_not_execute_remote_commands() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    firewall = OpenWrtFirewallExecutor(
        executor=executor,
    )

    firewall.build_commands(make_policy())

    executor.run.assert_not_called()


def test_apply_executes_all_commands() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.return_value = Mock(
        returncode=0,
        stdout="",
        stderr="",
    )

    firewall = OpenWrtFirewallExecutor(
        executor=executor,
    )

    policy = make_policy()
    commands = firewall.build_commands(policy)

    firewall.apply(policy)

    assert executor.run.call_count == len(commands)


def test_apply_ignores_missing_chain() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    def run(command: list[str]) -> Mock:
        if command[1] == "-N":
            return Mock(
                returncode=1,
                stdout="",
                stderr="iptables: Chain already exists.",
            )

        return Mock(
            returncode=0,
            stdout="",
            stderr="",
        )

    executor.run.side_effect = run

    firewall = OpenWrtFirewallExecutor(
        executor=executor,
    )

    policy = make_policy()
    commands = firewall.build_commands(policy)

    firewall.apply(policy)

    assert executor.run.call_count == len(commands)


def test_apply_ignores_missing_forward_jump() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    def run(command: list[str]) -> Mock:
        if command[1] == "-D":
            return Mock(
                returncode=1,
                stdout="",
                stderr="iptables: Bad rule",
            )

        return Mock(
            returncode=0,
            stdout="",
            stderr="",
        )

    executor.run.side_effect = run

    firewall = OpenWrtFirewallExecutor(
        executor=executor,
    )

    policy = make_policy()
    commands = firewall.build_commands(policy)

    firewall.apply(policy)

    assert executor.run.call_count == len(commands)


def test_apply_rejects_unexpected_command_failure() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    def run(command: list[str]) -> Mock:
        if command[1] == "-A" and command[2] == "MAXVPN_LAN_FORWARD":
            return Mock(
                returncode=1,
                stdout="",
                stderr="permission denied",
            )

        return Mock(
            returncode=0,
            stdout="",
            stderr="",
        )

    executor.run.side_effect = run

    firewall = OpenWrtFirewallExecutor(
        executor=executor,
    )

    try:
        firewall.apply(make_policy())
    except RuntimeError as exc:
        assert "OpenWrt firewall command failed" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")


def test_apply_ignores_missing_forward_jump_no_chain_message() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    def run(command: list[str]) -> Mock:
        if command[1] == "-D":
            return Mock(
                returncode=1,
                stdout="",
                stderr="iptables: No chain/target/match by that name.",
            )

        return Mock(
            returncode=0,
            stdout="",
            stderr="",
        )

    executor.run.side_effect = run

    firewall = OpenWrtFirewallExecutor(
        executor=executor,
    )

    policy = make_policy()
    commands = firewall.build_commands(policy)

    firewall.apply(policy)

    assert executor.run.call_count == len(commands)
