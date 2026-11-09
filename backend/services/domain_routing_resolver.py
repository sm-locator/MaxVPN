from __future__ import annotations

import socket
from ipaddress import ip_address
from typing import Iterable


class DomainRoutingResolutionError(RuntimeError):
    """Raised when a domain cannot be resolved for routing purposes."""


class DomainRoutingResolver:
    """
    Resolves a domain to its currently available IP addresses.

    The resolver intentionally uses the system resolver. This keeps the first
    implementation independent of OpenWrt runtime and makes it deterministic
    and easy to test.
    """

    def resolve(self, domain: str) -> tuple[str, ...]:
        normalized = self._normalize_domain(domain)

        try:
            results = socket.getaddrinfo(
                normalized,
                None,
                socket.AF_UNSPEC,
                socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise DomainRoutingResolutionError(
                f"failed to resolve domain {normalized!r}"
            ) from exc

        addresses = {str(ip_address(sockaddr[0])) for _, _, _, _, sockaddr in results}

        if not addresses:
            raise DomainRoutingResolutionError(
                f"domain {normalized!r} resolved to no addresses"
            )

        return tuple(sorted(addresses))

    @staticmethod
    def resolve_many(domains: Iterable[str]) -> dict[str, tuple[str, ...]]:
        resolver = DomainRoutingResolver()
        return {
            resolver._normalize_domain(domain): resolver.resolve(domain)
            for domain in domains
        }

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        value = domain.strip().lower().rstrip(".")

        if value.startswith("*."):
            value = value[2:]

        if not value or "." not in value:
            raise ValueError("domain must contain at least two labels")

        return value
