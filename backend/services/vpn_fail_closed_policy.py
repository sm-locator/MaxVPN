from __future__ import annotations

from dataclasses import dataclass

from backend.models.vpn_traffic_policy import VpnTrafficPolicy


@dataclass(frozen=True, slots=True)
class VpnFailClosedPolicy:
    """
    Produces the desired fail-closed traffic policy.
    """

    def build(
        self,
        *,
        lan_interface: str = "br-lan",
        vpn_interface: str = "WireGuard",
        wan_interface: str = "eth1",
    ) -> VpnTrafficPolicy:
        return VpnTrafficPolicy(
            lan_interface=lan_interface,
            vpn_interface=vpn_interface,
            wan_interface=wan_interface,
            allow_lan_to_vpn=True,
            allow_lan_to_wan=False,
            allow_lan_to_wan_ipv6=False,
            allow_vpn_endpoint_via_wan=True,
        )
