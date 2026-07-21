from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.database.base import Base

TEST_DATABASE_URL = "postgresql+psycopg://maxvpn:MaxVPN2026@database:5432/maxvpn_test"


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL)

    yield engine

    engine.dispose()


@pytest.fixture(scope="session")
def session_factory(engine):
    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )


def truncate_all_tables(session: Session) -> None:
    table_names = ", ".join(
        table.name for table in reversed(Base.metadata.sorted_tables)
    )

    session.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
    session.commit()


@pytest.fixture
def db_session(session_factory) -> Generator[Session, None, None]:
    session = session_factory()

    truncate_all_tables(session)

    try:
        yield session
    finally:
        session.rollback()
        session.close()
