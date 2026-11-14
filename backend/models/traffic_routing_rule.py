from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from ipaddress import (
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
    ip_address,
    ip_network,
)


class TrafficRoute(str, Enum):
    VPN = "vpn"
    DIRECT = "direct"


class TrafficTargetType(str, Enum):
    DOMAIN = "domain"
    CIDR = "cidr"


class TrafficAddressFamily(str, Enum):
    ANY = "any"
    IPV4 = "ipv4"
    IPV6 = "ipv6"


TrafficIP = IPv4Address | IPv6Address
TrafficNetwork = IPv4Network | IPv6Network


@dataclass(frozen=True, slots=True)
class TrafficRoutingRule:
    target_type: TrafficTargetType
    target: str
    action: TrafficRoute
    priority: int = 100
    address_family: TrafficAddressFamily = TrafficAddressFamily.ANY
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.priority < 0:
            raise ValueError("priority must be non-negative")

        normalized_target = self._normalize_target(
            self.target,
            self.target_type,
        )

        object.__setattr__(
            self,
            "target",
            normalized_target,
        )

    @staticmethod
    def _normalize_target(
        target: str,
        target_type: TrafficTargetType,
    ) -> str:
        value = target.strip()

        if not value:
            raise ValueError("target must not be empty")

        if target_type is TrafficTargetType.DOMAIN:
            return TrafficRoutingRule._normalize_domain(value)

        network = ip_network(value, strict=False)
        return str(network)

    @staticmethod
    def _normalize_domain(target: str) -> str:
        value = target.strip().lower().rstrip(".")

        if value.startswith("*."):
            value = value[2:]

        if not value:
            raise ValueError("domain must not be empty")

        if any(character in value for character in "/?#@:"):
            raise ValueError("domain must contain only a hostname")

        if "://" in value or "@" in value:
            raise ValueError("domain must contain only a hostname")

        if len(value) > 253:
            raise ValueError("domain is too long")

        labels = value.split(".")

        if len(labels) < 2:
            raise ValueError("domain must contain at least two labels")

        if any(not label for label in labels):
            raise ValueError("domain contains an empty label")

        for label in labels:
            if len(label) > 63:
                raise ValueError("domain label is too long")

            if label[0] == "-" or label[-1] == "-":
                raise ValueError("domain labels must not start or end with '-'")

            if not all(character.isalnum() or character == "-" for character in label):
                raise ValueError("domain contains invalid characters")

        return value

    def matches_domain(self, domain: str) -> bool:
        if self.target_type is not TrafficTargetType.DOMAIN:
            return False

        if not self.enabled:
            return False

        normalized = domain.strip().lower().rstrip(".")

        if not normalized:
            return False

        if self.address_family is not TrafficAddressFamily.ANY:
            return False

        return normalized == self.target or normalized.endswith(f".{self.target}")

    def matches_ip(self, value: str | TrafficIP) -> bool:
        if self.target_type is not TrafficTargetType.CIDR:
            return False

        if not self.enabled:
            return False

        address = ip_address(value)

        if self.address_family is TrafficAddressFamily.IPV4 and address.version != 4:
            return False

        if self.address_family is TrafficAddressFamily.IPV6 and address.version != 6:
            return False

        network: TrafficNetwork = ip_network(
            self.target,
            strict=False,
        )

        return address in network
