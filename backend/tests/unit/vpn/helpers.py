from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
from unittest.mock import Mock

from app.vpn.ip_allocator import IPAllocator
from app.vpn.models import (
    WireGuardClient,
)
from app.vpn.wireguard.keys import WireGuardKeyPair
from app.vpn.wireguard.manager import WireGuardManager
from app.vpn.wireguard.server_settings import WireGuardServerSettings
from app.vpn.wireguard.settings import WireGuardSettings


def create_client(
    *,
    name: str = "phone",
    private_key: str = "private_key",
    public_key: str = "public_key",
    ip_address: IPv4Address = IPv4Address("10.8.0.2"),
    description: str | None = None,
    enabled: bool = True,
) -> WireGuardClient:
    return WireGuardClient(
        name=name,
        private_key=private_key,
        public_key=public_key,
        ip_address=ip_address,
        description=description,
        enabled=enabled,
    )


def create_server() -> WireGuardServerSettings:
    return WireGuardServerSettings(
        server_public_key="server_public_key",
        endpoint="vpn.example.com:51820",
        dns="1.1.1.1",
        allowed_ips="0.0.0.0/0",
        persistent_keepalive=25,
    )


def create_key_pair() -> WireGuardKeyPair:
    return WireGuardKeyPair(
        private_key="private_key",
        public_key="public_key",
    )


@dataclass
class Dependencies:
    repository: Mock
    allocator: Mock
    key_generator: Mock
    config_generator: Mock
    peer_manager: Mock


def create_dependencies() -> Dependencies:
    return Dependencies(
        repository=Mock(),
        allocator=Mock(spec=IPAllocator),
        key_generator=Mock(),
        config_generator=Mock(),
        peer_manager=Mock(),
    )


def create_manager(
    deps: Dependencies | None = None,
) -> WireGuardManager:
    deps = deps or create_dependencies()

    return WireGuardManager(
        settings=WireGuardSettings(
            network=IPv4Network("10.8.0.0/24"),
        ),
        repository=deps.repository,
        allocator=deps.allocator,
        key_generator=deps.key_generator,
        config_generator=deps.config_generator,
        peer_manager=deps.peer_manager,
    )
