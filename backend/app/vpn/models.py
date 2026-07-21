from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Address


@dataclass(slots=True, frozen=True)
class WireGuardClientConfig:
    private_key: str
    client_ip: str
    dns: str
    server_public_key: str
    endpoint: str
    allowed_ips: str = "0.0.0.0/0, ::/0"
    persistent_keepalive: int = 25


@dataclass(slots=True)
class WireGuardClient:
    name: str
    public_key: str
    ip_address: IPv4Address
