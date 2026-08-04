from ipaddress import IPv4Address
from typing import Protocol

from app.vpn.models import WireGuardClient


class WireGuardClientRepository(Protocol):
    def get_used_addresses(self) -> set[IPv4Address]: ...

    def add(self, client: WireGuardClient) -> None: ...

    def get_by_name(self, name: str) -> WireGuardClient | None: ...

    def delete(self, client: WireGuardClient) -> None: ...


class WireGuardPeerManager(Protocol):
    def add_peer(
        self,
        public_key: str,
        address: IPv4Address,
    ) -> None: ...

    def remove_peer(
        self,
        public_key: str,
    ) -> None: ...
