from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.infrastructure.database.base import Base
from backend.infrastructure.database.models.server_model import ServerModel
from backend.infrastructure.database.repositories.sqlalchemy_client_repository import (
    SqlAlchemyClientRepository,
)
from backend.models.client import Client


def make_repository():
    engine = create_engine("sqlite:///:memory:")

    Base.metadata.create_all(engine)

    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    session.add(
        ServerModel(
            id=1,
            name="Warsaw-1",
            country="PL",
            city="Warsaw",
            endpoint="pl1.maxvpn.local:51820",
            public_key="server-public-key",
        )
    )
    session.commit()

    return session, SqlAlchemyClientRepository(session)


def make_client() -> Client:
    return Client(
        id=None,
        name="phone",
        server_id=1,
        private_key="private-key",
        public_key="public-key",
        address="10.100.0.2/32",
    )


def test_repository_add_and_get_by_name():
    session, repository = make_repository()

    client = make_client()

    repository.add(client)
    session.commit()

    assert client.id is not None

    result = repository.get_by_name("phone")

    assert result is not None
    assert result.id == client.id
    assert result.server_id == 1
    assert result.public_key == "public-key"
    assert result.address == "10.100.0.2/32"


def test_repository_returns_used_addresses():
    session, repository = make_repository()

    repository.add(make_client())
    session.commit()

    assert repository.get_used_addresses() == {"10.100.0.2/32"}


def test_repository_delete():
    session, repository = make_repository()

    client = make_client()

    repository.add(client)
    session.commit()

    repository.delete(client)
    session.commit()

    assert repository.get_by_name("phone") is None
