from __future__ import annotations

from dataclasses import dataclass

from backend.models.openwrt_network_info import OpenWrtNetworkInfo


@dataclass(slots=True)
class MaxVPNInstallationContext:
    network: OpenWrtNetworkInfo | None = None
