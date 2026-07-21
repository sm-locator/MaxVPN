from ipaddress import IPv4Address

from sqlalchemy import select

from app.database.models.wireguard_client import (
    WireGuardClient as ORMWireGuardClient,
)
from app.repositories.sqlalchemy.wireguard_client import (
    SQLAlchemyWireGuardClientRepository,
)
from app.vpn.models import WireGuardClient


def test_add_client(db_session):
    repository = SQLAlchemyWireGuardClientRepository(db_session)

    client = WireGuardClient(
        name="phone",
        public_key="public_key",
        ip_address=IPv4Address("10.8.0.2"),
    )

    repository.add(client)

    db_session.commit()

    saved_client = db_session.scalar(
        select(ORMWireGuardClient).where(
            ORMWireGuardClient.name == "phone",
        )
    )

    assert saved_client is not None
    assert saved_client.name == "phone"
    assert saved_client.public_key == "public_key"
    assert saved_client.ip_address == IPv4Address("10.8.0.2")


def test_get_used_addresses_returns_saved_addresses(db_session):
    repository = SQLAlchemyWireGuardClientRepository(db_session)

    repository.add(
        WireGuardClient(
            name="phone",
            public_key="key1",
            ip_address=IPv4Address("10.8.0.2"),
        )
    )

    repository.add(
        WireGuardClient(
            name="laptop",
            public_key="key2",
            ip_address=IPv4Address("10.8.0.3"),
        )
    )

    db_session.commit()

    used_addresses = repository.get_used_addresses()

    assert used_addresses == {
        IPv4Address("10.8.0.2"),
        IPv4Address("10.8.0.3"),
    }


def test_get_used_addresses_returns_empty_set(db_session):
    repository = SQLAlchemyWireGuardClientRepository(db_session)

    assert repository.get_used_addresses() == set()
