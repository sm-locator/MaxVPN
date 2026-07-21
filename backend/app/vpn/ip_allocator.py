from __future__ import annotations

from ipaddress import IPv4Address, IPv4Network

from app.vpn.exceptions import NoAvailableIPAddressError


class IPAllocator:
    """Allocates IP addresses from a network."""

    def allocate(
        self,
        *,
        network: IPv4Network,
        used_addresses: set[IPv4Address],
        reserved_addresses: set[IPv4Address] | None = None,
    ) -> IPv4Address:
        if reserved_addresses is None:
            reserved_addresses = set()

        occupied_addresses = used_addresses | reserved_addresses

        for address in network.hosts():
            if address not in occupied_addresses:
                return address

        raise NoAvailableIPAddressError("No available IP addresses.")
