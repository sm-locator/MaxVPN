from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VpnTrafficPolicy:
    """
    Desired fail-closed traffic policy.

    LAN traffic may use the VPN interface only.
    The VPN endpoint itself must remain reachable through WAN.
    IPv6 WAN fallback is disabled.
    """

    lan_interface: str = "br-lan"
    vpn_interface: str = "WireGuard"
    wan_interface: str = "eth1"

    allow_lan_to_vpn: bool = True
    allow_lan_to_wan: bool = False
    allow_lan_to_wan_ipv6: bool = False
    allow_vpn_endpoint_via_wan: bool = True
