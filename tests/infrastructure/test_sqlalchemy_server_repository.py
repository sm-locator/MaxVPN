from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.infrastructure.database.base import Base
from backend.infrastructure.database.models.server_model import ServerModel
from backend.infrastructure.database.repositories.sqlalchemy_server_repository import (
    SqlAlchemyServerRepository,
)


def create_session():
    engine = create_engine("sqlite:///:memory:")

    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)

    return Session()


def test_repository_returns_all_servers():
    session = create_session()

    session.add_all(
        [
            ServerModel(
                id=1,
                name="Warsaw",
                country="PL",
                city="Warsaw",
                endpoint="pl.example.com:51820",
                public_key="server-public-key-1",
                online=True,
                maintenance=False,
                load=10,
                latency=25,
                max_load=80,
                max_devices=1000,
            ),
            ServerModel(
                id=2,
                name="Berlin",
                country="DE",
                city="Berlin",
                endpoint="de.example.com:51820",
                public_key="server-public-key-2",
                online=True,
                maintenance=False,
                load=20,
                latency=35,
                max_load=80,
                max_devices=1000,
            ),
        ]
    )

    session.commit()

    repository = SqlAlchemyServerRepository(session)

    servers = repository.get_all()

    assert len(servers) == 2

    assert servers[0].name == "Warsaw"
    assert servers[1].name == "Berlin"


def test_repository_returns_only_available_servers():
    session = create_session()

    session.add_all(
        [
            ServerModel(
                id=1,
                name="Warsaw",
                country="PL",
                city="Warsaw",
                endpoint="pl.example.com:51820",
                public_key="server-public-key-1",
                online=True,
                maintenance=False,
                load=10,
                latency=25,
                max_load=80,
                max_devices=1000,
            ),
            ServerModel(
                id=2,
                name="Offline",
                country="DE",
                city="Berlin",
                endpoint="de.example.com:51820",
                public_key="server-public-key-2",
                online=False,
                maintenance=False,
                load=20,
                latency=35,
                max_load=80,
                max_devices=1000,
            ),
            ServerModel(
                id=3,
                name="Maintenance",
                country="FR",
                city="Paris",
                endpoint="fr.example.com:51820",
                public_key="server-public-key-3",
                online=True,
                maintenance=True,
                load=15,
                latency=30,
                max_load=80,
                max_devices=1000,
            ),
        ]
    )

    session.commit()

    repository = SqlAlchemyServerRepository(session)

    servers = repository.get_available()

    assert len(servers) == 1
    assert servers[0].name == "Warsaw"
