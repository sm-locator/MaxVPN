from __future__ import annotations

from backend.application.use_cases.select_best_server import (
    SelectBestServerUseCase,
)
from backend.models.client_config import ClientConfig
from backend.models.peer import Peer
from backend.models.tunnel import Tunnel
from backend.policy.context import PolicyContext
from backend.ports.address_allocator import AddressAllocator
from backend.ports.key_provider import KeyProvider


class CreateClientUseCase:
    """
    Creates a complete VPN client configuration.
    """

    def __init__(
        self,
        select_server: SelectBestServerUseCase,
        key_provider: KeyProvider,
        address_allocator: AddressAllocator,
    ):
        self._select_server = select_server
        self._key_provider = key_provider
        self._address_allocator = address_allocator

    def execute(
        self,
        context: PolicyContext,
    ) -> ClientConfig | None:
        server = self._select_server.execute(context)

        if server is None:
            return None

        key_pair = self._key_provider.generate()
        address = self._address_allocator.allocate()

        tunnel = Tunnel(
            address=address,
        )

        peer = Peer(
            public_key=server.public_key,
            allowed_ips="0.0.0.0/0",
        )

        return ClientConfig(
            server=server,
            key_pair=key_pair,
            tunnel=tunnel,
            peer=peer,
        )
