from ipaddress import IPv4Address
from unittest.mock import Mock

from app.database.models.wireguard_client import WireGuardClient
from app.repositories.sqlalchemy.wireguard_client import (
    SQLAlchemyWireGuardClientRepository,
)


def test_get_used_addresses() -> None:
    session = Mock()

    session.scalars.return_value.all.return_value = [
        WireGuardClient(
            name="phone",
            public_key="public_key_1",
            ip_address="10.8.0.2",
        ),
        WireGuardClient(
            name="laptop",
            public_key="public_key_2",
            ip_address="10.8.0.3",
        ),
    ]

    repository = SQLAlchemyWireGuardClientRepository(session)

    assert repository.get_used_addresses() == {
        IPv4Address("10.8.0.2"),
        IPv4Address("10.8.0.3"),
    }

    session.scalars.assert_called_once()


def test_add_client() -> None:
    session = Mock()

    repository = SQLAlchemyWireGuardClientRepository(session)

    client = WireGuardClient(
        name="phone",
        public_key="public_key",
        ip_address="10.8.0.2",
    )

    repository.add(client)

    session.add.assert_called_once()

    saved_client = session.add.call_args.args[0]

    assert saved_client.name == "phone"
    assert saved_client.public_key == "public_key"
    assert saved_client.ip_address == "10.8.0.2"
