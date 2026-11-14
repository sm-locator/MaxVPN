from __future__ import annotations

from ipaddress import IPv4Network

from backend.ports.address_allocator import AddressAllocator
from backend.ports.client_repository import ClientRepository


class DatabaseAddressAllocator(AddressAllocator):
    """
    Allocates unique client addresses using persisted client state.
    """

    def __init__(
        self,
        client_repository: ClientRepository,
        network: str = "10.100.0.0/24",
        first_host: int = 2,
    ) -> None:
        self._client_repository = client_repository
        self._network = IPv4Network(network)
        self._first_host = first_host

    def allocate(self) -> str:
        used_addresses = self._client_repository.get_used_addresses()

        for address in self._network.hosts():
            if int(address) < int(self._network.network_address) + self._first_host:
                continue

            candidate = f"{address}/32"

            if candidate not in used_addresses:
                return candidate

        raise RuntimeError(f"No free client addresses in network {self._network}")
