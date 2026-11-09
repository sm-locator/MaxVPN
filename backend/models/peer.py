from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Peer:
    """
    WireGuard peer.
    """

    public_key: str

    allowed_ips: str

    persistent_keepalive: int = 25
