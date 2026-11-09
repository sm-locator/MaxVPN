from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Tunnel:
    """
    WireGuard tunnel configuration.
    """

    address: str

    dns: str = "1.1.1.1"

    mtu: int = 1420
