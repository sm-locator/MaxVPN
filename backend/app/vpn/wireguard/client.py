from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Address


@dataclass(slots=True, frozen=True)
class CreatedWireGuardClient:
    name: str
    ip_address: IPv4Address
    public_key: str
    config: str
