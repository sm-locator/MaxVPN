from ipaddress import IPv4Address, IPv4Network
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from app.database.models.wireguard_client import (
    WireGuardClient as ORMWireGuardClient,
)
from app.repositories.sqlalchemy.wireguard_client import (
    SQLAlchemyWireGuardClientRepository,
)
from app.vpn.ip_allocator import (
    IPAllocator,
    NoAvailableIPAddressError,
)
from app.vpn.wireguard.keys import WireGuardKeyPair
from app.vpn.wireguard.manager import WireGuardManager
from app.vpn.wireguard.server_settings import WireGuardServerSettings
from app.vpn.wireguard.settings import WireGuardSettings


def test_create_two_clients_get_different_addresses(db_session):
    settings = WireGuardSettings(
        network=IPv4Network("10.8.0.0/24"),
        reserved_addresses={
            IPv4Address("10.8.0.1"),
        },
    )

    repository = SQLAlchemyWireGuardClientRepository(db_session)

    allocator = IPAllocator()

    key_generator = Mock()
    config_generator = Mock()

    key_generator.generate.side_effect = [
        WireGuardKeyPair(
            private_key="private1",
            public_key="public1",
        ),
        WireGuardKeyPair(
            private_key="private2",
            public_key="public2",
        ),
    ]

    config_generator.generate.side_effect = [
        "config1",
        "config2",
    ]

    server = WireGuardServerSettings(
        server_public_key="server_public_key",
        endpoint="vpn.example.com:51820",
        dns="1.1.1.1",
        allowed_ips="0.0.0.0/0",
        persistent_keepalive=25,
    )

    manager = WireGuardManager(
        settings=settings,
        repository=repository,
        allocator=allocator,
        key_generator=key_generator,
        config_generator=config_generator,
    )

    # Первый клиент
    manager.create_client(
        client_name="phone",
        server=server,
    )

    # Делаем запись видимой для следующего вызова
    db_session.flush()

    # Второй клиент
    manager.create_client(
        client_name="laptop",
        server=server,
    )

    db_session.flush()

    clients = (
        db_session.execute(
            select(ORMWireGuardClient).order_by(ORMWireGuardClient.ip_address)
        )
        .scalars()
        .all()
    )

    assert len(clients) == 2

    assert clients[0].name == "phone"
    assert clients[0].public_key == "public1"
    assert clients[0].ip_address == IPv4Address("10.8.0.2")

    assert clients[1].name == "laptop"
    assert clients[1].public_key == "public2"
    assert clients[1].ip_address == IPv4Address("10.8.0.3")


def test_create_client_when_network_is_full_raises_error(db_session):
    settings = WireGuardSettings(
        network=IPv4Network("10.8.0.0/30"),
        reserved_addresses={
            IPv4Address("10.8.0.1"),
        },
    )

    repository = SQLAlchemyWireGuardClientRepository(db_session)

    allocator = IPAllocator()

    key_generator = Mock()
    config_generator = Mock()

    key_generator.generate.side_effect = [
        WireGuardKeyPair(
            private_key="private1",
            public_key="public1",
        ),
        WireGuardKeyPair(
            private_key="private2",
            public_key="public2",
        ),
    ]

    config_generator.generate.side_effect = [
        "config1",
        "config2",
    ]

    server = WireGuardServerSettings(
        server_public_key="server_public_key",
        endpoint="vpn.example.com:51820",
        dns="1.1.1.1",
        allowed_ips="0.0.0.0/0",
        persistent_keepalive=25,
    )

    manager = WireGuardManager(
        settings=settings,
        repository=repository,
        allocator=allocator,
        key_generator=key_generator,
        config_generator=config_generator,
    )

    # Единственный доступный IP: 10.8.0.2
    manager.create_client(
        client_name="phone",
        server=server,
    )

    # Делаем запись видимой для следующего запроса
    db_session.flush()

    # Второго клиента создать уже невозможно
    with pytest.raises(NoAvailableIPAddressError):
        manager.create_client(
            client_name="laptop",
            server=server,
        )

    clients = db_session.execute(select(ORMWireGuardClient)).scalars().all()

    assert len(clients) == 1
    assert clients[0].name == "phone"
    assert clients[0].ip_address == IPv4Address("10.8.0.2")
