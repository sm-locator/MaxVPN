from backend.models.vpn_traffic_policy import VpnTrafficPolicy
from backend.services.vpn_fail_closed_policy import VpnFailClosedPolicy


def test_build_returns_fail_closed_policy() -> None:
    policy = VpnFailClosedPolicy()

    result = policy.build()

    assert isinstance(result, VpnTrafficPolicy)

    assert result.lan_interface == "br-lan"
    assert result.vpn_interface == "WireGuard"
    assert result.wan_interface == "eth1"

    assert result.allow_lan_to_vpn is True
    assert result.allow_lan_to_wan is False
    assert result.allow_lan_to_wan_ipv6 is False
    assert result.allow_vpn_endpoint_via_wan is True


def test_build_accepts_interface_overrides() -> None:
    policy = VpnFailClosedPolicy()

    result = policy.build(
        lan_interface="lan0",
        vpn_interface="wg0",
        wan_interface="wan0",
    )

    assert result.lan_interface == "lan0"
    assert result.vpn_interface == "wg0"
    assert result.wan_interface == "wan0"

    assert result.allow_lan_to_vpn is True
    assert result.allow_lan_to_wan is False
    assert result.allow_lan_to_wan_ipv6 is False
    assert result.allow_vpn_endpoint_via_wan is True
