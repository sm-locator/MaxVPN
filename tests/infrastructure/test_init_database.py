from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from backend.infrastructure.database.init_db import init_database
from backend.infrastructure.database.models.server_model import ServerModel


def test_init_database_creates_schema_and_seeds():
    engine = create_engine("sqlite:///:memory:")

    Session = sessionmaker(bind=engine)

    init_database(
        engine_override=engine,
        session_factory_override=Session,
    )

    session = Session()

    servers = session.scalars(select(ServerModel)).all()

    assert len(servers) == 3

    names = {server.name for server in servers}

    assert names == {
        "Warsaw-1",
        "Frankfurt-1",
        "Paris-1",
    }

    session.close()


def test_init_database_refuses_incompatible_api_schema_before_writes():
    engine = create_engine("sqlite:///:memory:")
    session_factory = Mock()
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE servers (id INTEGER, hostname TEXT)"))

    with pytest.raises(RuntimeError, match="Legacy CLI database schema"):
        init_database(engine_override=engine, session_factory_override=session_factory)

    assert inspect(engine).get_table_names() == ["servers"]
    session_factory.assert_not_called()
