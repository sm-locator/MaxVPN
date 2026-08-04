from __future__ import annotations

from app.vpn.exceptions import ClientNotFoundError
from app.vpn.ip_allocator import IPAllocator
from app.vpn.models import (
    WireGuardClient,
    WireGuardClientConfig,
)
from app.vpn.repositories import (
    WireGuardClientRepository,
    WireGuardPeerManager,
)
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
        peer_manager: WireGuardPeerManager,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._allocator = allocator
        self._key_generator = key_generator
        self._config_generator = config_generator
        self._peer_manager = peer_manager

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
            private_key=keys.private_key,
            public_key=keys.public_key,
            ip_address=client_ip,
        )

        self._repository.add(client)

        try:
            self._peer_manager.add_peer(
                public_key=client.public_key,
                address=client.ip_address,
            )
        except Exception:
            self._repository.delete(client)
            raise

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

    def delete_client(
        self,
        client_name: str,
    ) -> None:
        client = self._get_required_client(client_name)

        self._peer_manager.remove_peer(client.public_key)
        self._repository.delete(client)

    def get_client_config(
        self,
        client_name: str,
        server: WireGuardServerSettings,
    ) -> str:
        client = self._get_required_client(client_name)

        config = WireGuardClientConfig(
            private_key=client.private_key,
            client_ip=f"{client.ip_address}/32",
            dns=server.dns,
            server_public_key=server.server_public_key,
            endpoint=server.endpoint,
            allowed_ips=server.allowed_ips,
            persistent_keepalive=server.persistent_keepalive,
        )

        return self._config_generator.generate(config)

    def list_clients(self) -> list[WireGuardClient]:
        return self._repository.list_clients()

    def get_client(
        self,
        client_name: str,
    ) -> WireGuardClient:
        return self._get_required_client(client_name)

    def update_client(
        self,
        client_name: str,
        name: str,
        description: str | None,
        enabled: bool,
    ) -> WireGuardClient:
        client = self._repository.get_by_name(client_name)

        if client is None:
            raise ClientNotFoundError(f"WireGuard client '{client_name}' not found.")

        client.update(
            name=name,
            description=description,
            enabled=enabled,
        )

        self._repository.update(
            client_name=client_name,
            client=client,
        )

        return client

    def _get_required_client(
        self,
        client_name: str,
    ) -> WireGuardClient:
        client = self._repository.get_by_name(client_name)

        if client is None:
            raise ClientNotFoundError(f"WireGuard client '{client_name}' not found.")

        return client

    def disable_client(
        self,
        client_name: str,
    ) -> None:
        client = self._get_required_client(client_name)

        self._peer_manager.remove_peer(client.public_key)

        client.enabled = False

        self._repository.update(
            client_name=client_name,
            client=client,
        )

    def enable_client(
        self,
        client_name: str,
    ) -> None:
        client = self._get_required_client(client_name)

        self._peer_manager.add_peer(
            public_key=client.public_key,
            address=client.ip_address,
        )

        client.enabled = True

        self._repository.update(
            client_name=client_name,
            client=client,
        )
