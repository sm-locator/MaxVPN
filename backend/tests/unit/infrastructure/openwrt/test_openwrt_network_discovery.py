from unittest.mock import Mock

import pytest
from backend.infrastructure.openwrt.openwrt_network_discovery import (
    OpenWrtNetworkDiscovery,
)
from backend.models.command_result import CommandResult
from backend.models.openwrt_network_info import OpenWrtNetworkInfo
from backend.ports.remote_command_executor import RemoteCommandExecutor

LAN_JSON = """
{
    "l3_device": "br-lan",
    "device": "br-lan",
    "ipv4-address": [
        {
            "address": "192.168.8.1",
            "mask": 24
        }
    ]
}
"""

WAN_JSON = """
{
    "l3_device": "eth1",
    "device": "eth1",
    "ipv4-address": [
        {
            "address": "46.48.56.64",
            "mask": 24
        }
    ]
}
"""

DEFAULT_ROUTE = """
default via 46.48.56.1 dev eth1 proto static src 46.48.56.64 metric 10
"""

AWG_OUTPUT = """
interface: WireGuard
  public key: test
  private key: (hidden)
  listening port: 41838

peer: test-peer
  endpoint: 109.172.55.99:51820
  allowed ips: 0.0.0.0/0
  latest handshake: 10 seconds ago
"""


def make_result(stdout: str, returncode: int = 0) -> CommandResult:
    return CommandResult(
        stdout=stdout,
        stderr="",
        returncode=returncode,
    )


def make_executor() -> Mock:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        make_result(LAN_JSON),
        make_result(WAN_JSON),
        make_result(DEFAULT_ROUTE),
        make_result(AWG_OUTPUT),
    ]

    return executor


def test_discover_returns_current_openwrt_network_info() -> None:
    executor = make_executor()

    discovery = OpenWrtNetworkDiscovery(
        executor=executor,
    )

    result = discovery.discover()

    assert result == OpenWrtNetworkInfo(
        lan_interface="br-lan",
        lan_ipv4="192.168.8.1/24",
        wan_interface="eth1",
        wan_ipv4="46.48.56.64/24",
        wan_gateway="46.48.56.1",
        vpn_interface="WireGuard",
        vpn_endpoint="109.172.55.99:51820",
    )


def test_discover_uses_only_read_only_commands() -> None:
    executor = make_executor()

    OpenWrtNetworkDiscovery(
        executor=executor,
    ).discover()

    commands = [call.args[0] for call in executor.run.call_args_list]

    assert commands == [
        ["ubus", "call", "network.interface.lan", "status"],
        ["ubus", "call", "network.interface.wan", "status"],
        ["ip", "-4", "route", "show", "default"],
        ["awg", "show"],
    ]

    text = " ".join(" ".join(command) for command in commands)

    forbidden = (
        "ip route add",
        "ip rule add",
        "iptables",
        "uci set",
        "service ",
        "reload",
        "restart",
    )

    for item in forbidden:
        assert item not in text


def test_discover_allows_awg_to_be_unavailable() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        make_result(LAN_JSON),
        make_result(WAN_JSON),
        make_result(DEFAULT_ROUTE),
        make_result("", returncode=1),
    ]

    result = OpenWrtNetworkDiscovery(
        executor=executor,
    ).discover()

    assert result.vpn_interface is None
    assert result.vpn_endpoint is None


def test_discover_rejects_missing_default_gateway() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        make_result(LAN_JSON),
        make_result(WAN_JSON),
        make_result("10.0.0.0/24 dev eth1"),
        make_result(AWG_OUTPUT),
    ]

    with pytest.raises(
        RuntimeError,
        match="default_gateway_missing",
    ):
        OpenWrtNetworkDiscovery(
            executor=executor,
        ).discover()


def test_discover_rejects_missing_wan_ipv4() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    wan_without_ipv4 = """
    {
        "l3_device": "eth1",
        "device": "eth1",
        "ipv4-address": []
    }
    """

    executor.run.side_effect = [
        make_result(LAN_JSON),
        make_result(wan_without_ipv4),
        make_result(DEFAULT_ROUTE),
        make_result(AWG_OUTPUT),
    ]

    with pytest.raises(
        RuntimeError,
        match="wan_ipv4_missing",
    ):
        OpenWrtNetworkDiscovery(
            executor=executor,
        ).discover()
