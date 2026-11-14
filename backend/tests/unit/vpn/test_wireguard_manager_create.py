from ipaddress import IPv4Address, IPv4Network

import pytest

from app.vpn.models import WireGuardClientConfig
from tests.unit.vpn.helpers import (
    create_dependencies,
    create_key_pair,
    create_manager,
    create_server,
)


def test_create_client() -> None:
    deps = create_dependencies()

    keys = create_key_pair()

    server = create_server()

    deps.repository.get_used_addresses.return_value = set()

    deps.allocator.allocate.return_value = IPv4Address("10.8.0.2")

    deps.key_generator.generate.return_value = keys

    deps.config_generator.generate.return_value = (
        "[Interface]\nPrivateKey = private_key"
    )

    manager = create_manager(deps)

    result = manager.create_client(
        client_name="phone",
        server=server,
    )

    assert result.name == "phone"
    assert result.ip_address == IPv4Address("10.8.0.2")
    assert result.public_key == "public_key"
    assert result.config == "[Interface]\nPrivateKey = private_key"

    deps.repository.get_used_addresses.assert_called_once()

    deps.allocator.allocate.assert_called_once_with(
        network=IPv4Network("10.8.0.0/24"),
        used_addresses=set(),
        reserved_addresses=set(),
    )

    deps.key_generator.generate.assert_called_once()

    deps.config_generator.generate.assert_called_once_with(
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

    deps.repository.add.assert_called_once()

    deps.peer_manager.add_peer.assert_called_once_with(
        public_key="public_key",
        address=IPv4Address("10.8.0.2"),
    )

    saved_client = deps.repository.add.call_args.args[0]

    assert saved_client.name == "phone"
    assert saved_client.public_key == "public_key"
    assert saved_client.ip_address == IPv4Address("10.8.0.2")


def test_create_client_rolls_back_repository_when_add_peer_fails() -> None:
    deps = create_dependencies()

    keys = create_key_pair()

    server = create_server()

    deps.repository.get_used_addresses.return_value = set()
    deps.allocator.allocate.return_value = IPv4Address("10.8.0.2")
    deps.key_generator.generate.return_value = keys
    deps.config_generator.generate.return_value = (
        "[Interface]\nPrivateKey = private_key"
    )

    deps.peer_manager.add_peer.side_effect = RuntimeError("wg failed")

    manager = create_manager(deps)

    with pytest.raises(RuntimeError, match="wg failed"):
        manager.create_client(
            client_name="phone",
            server=server,
        )

    saved_client = deps.repository.add.call_args.args[0]

    deps.repository.delete.assert_called_once_with(saved_client)
