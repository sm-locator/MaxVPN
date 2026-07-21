from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WireGuardServerSettings:
    server_public_key: str
    endpoint: str
    dns: str
    allowed_ips: str
    persistent_keepalive: int
