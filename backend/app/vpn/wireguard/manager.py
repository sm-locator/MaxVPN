from __future__ import annotations

from app.vpn.ip_allocator import IPAllocator
from app.vpn.models import (
    WireGuardClient,
    WireGuardClientConfig,
)
from app.vpn.repositories import WireGuardClientRepository
from app.vpn.wireguard.client import CreatedWireGuardClient
from app.vpn.wireguard.config import WireGuardConfigGenerator
from app.vpn.wireguard.keys import (
    WireGuardKeyGenerator,
)
from app.vpn.wireguard.server_settings import WireGuardServerSettings
from app.vpn.wireguard.settings import WireGuardSettings


class WireGuardManager:
    """High-level service for WireGuard operations."""

    def __init__(
        self,
        settings: WireGuardSettings,
        repository: WireGuardClientRepository,
        allocator: IPAllocator,
        key_generator: WireGuardKeyGenerator,
        config_generator: WireGuardConfigGenerator,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._allocator = allocator
        self._key_generator = key_generator
        self._config_generator = config_generator

    def create_client(
        self,
        client_name: str,
        server: WireGuardServerSettings,
    ) -> CreatedWireGuardClient:
        """Generate a WireGuard key pair and client configuration."""

        used_addresses = self._repository.get_used_addresses()

        client_ip = self._allocator.allocate(
            network=self._settings.network,
            used_addresses=used_addresses,
            reserved_addresses=self._settings.reserved_addresses,
        )

        keys = self._key_generator.generate()

        client = WireGuardClient(
            name=client_name,
            public_key=keys.public_key,
            ip_address=client_ip,
        )

        self._repository.add(client)

        config = WireGuardClientConfig(
            private_key=keys.private_key,
            client_ip=f"{client_ip}/32",
            dns=server.dns,
            server_public_key=server.server_public_key,
            endpoint=server.endpoint,
            allowed_ips=server.allowed_ips,
            persistent_keepalive=server.persistent_keepalive,
        )

        client_config = self._config_generator.generate(config)

        return CreatedWireGuardClient(
            name=client.name,
            ip_address=client.ip_address,
            public_key=client.public_key,
            config=client_config,
        )
