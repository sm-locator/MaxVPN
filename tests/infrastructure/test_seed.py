from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.infrastructure.database.base import Base
from backend.infrastructure.database.models.server_model import ServerModel
from backend.infrastructure.database.seeds.seed import seed_database


def create_session():
    engine = create_engine("sqlite:///:memory:")

    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)

    return Session()


def test_seed_database_populates_empty_database():
    session = create_session()

    seed_database(session)

    servers = session.scalars(select(ServerModel)).all()

    assert len(servers) == 3

    assert servers[0].name == "Warsaw-1"
    assert servers[1].name == "Frankfurt-1"
    assert servers[2].name == "Paris-1"


def test_seed_database_is_idempotent():
    session = create_session()

    seed_database(session)
    seed_database(session)

    servers = session.scalars(select(ServerModel)).all()

    assert len(servers) == 3
