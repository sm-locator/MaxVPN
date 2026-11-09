from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OpenWrtNetworkInfo:
    lan_interface: str
    lan_ipv4: str
    wan_interface: str
    wan_ipv4: str
    wan_gateway: str
    vpn_interface: str | None
    vpn_endpoint: str | None
