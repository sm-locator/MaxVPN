from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv4Network


@dataclass(frozen=True)
class WireGuardSettings:
    network: IPv4Network
    reserved_addresses: set[IPv4Address] = field(default_factory=set)
