from ipaddress import IPv4Address, IPv4Network
from unittest.mock import Mock

from app.vpn.ip_allocator import IPAllocator
from app.vpn.models import WireGuardClientConfig
from app.vpn.wireguard.keys import WireGuardKeyPair
from app.vpn.wireguard.manager import WireGuardManager
from app.vpn.wireguard.server_settings import WireGuardServerSettings
from app.vpn.wireguard.settings import WireGuardSettings


def test_create_client() -> None:
    settings = WireGuardSettings(
        network=IPv4Network("10.8.0.0/24"),
    )

    repository = Mock()
    allocator = Mock(spec=IPAllocator)
    key_generator = Mock()
    config_generator = Mock()

    keys = WireGuardKeyPair(
        private_key="private_key",
        public_key="public_key",
    )

    server = WireGuardServerSettings(
        server_public_key="server_public_key",
        endpoint="vpn.example.com:51820",
        dns="1.1.1.1",
        allowed_ips="0.0.0.0/0",
        persistent_keepalive=25,
    )

    repository.get_used_addresses.return_value = set()

    allocator.allocate.return_value = IPv4Address("10.8.0.2")

    key_generator.generate.return_value = keys

    config_generator.generate.return_value = "[Interface]\nPrivateKey = private_key"

    manager = WireGuardManager(
        settings=settings,
        repository=repository,
        allocator=allocator,
        key_generator=key_generator,
        config_generator=config_generator,
    )

    result = manager.create_client(
        client_name="phone",
        server=server,
    )

    assert result.name == "phone"
    assert result.ip_address == IPv4Address("10.8.0.2")
    assert result.public_key == "public_key"
    assert result.config == "[Interface]\nPrivateKey = private_key"

    repository.get_used_addresses.assert_called_once()

    allocator.allocate.assert_called_once_with(
        network=IPv4Network("10.8.0.0/24"),
        used_addresses=set(),
        reserved_addresses=set(),
    )

    key_generator.generate.assert_called_once()

    config_generator.generate.assert_called_once_with(
        WireGuardClientConfig(
            private_key="private_key",
            client_ip="10.8.0.2/32",
            dns="1.1.1.1",
            server_public_key="server_public_key",
            endpoint="vpn.example.com:51820",
            allowed_ips="0.0.0.0/0",
            persistent_keepalive=25,
        )
    )

    repository.add.assert_called_once()

    saved_client = repository.add.call_args.args[0]

    assert saved_client.name == "phone"
    assert saved_client.public_key == "public_key"
    assert saved_client.ip_address == IPv4Address("10.8.0.2")
