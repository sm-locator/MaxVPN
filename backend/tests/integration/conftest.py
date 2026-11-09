import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session, sessionmaker

from app.database.base import Base

TEST_DATABASE_NAME = "maxvpn_test"


def _test_database_url() -> URL:
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        raise pytest.UsageError(
            "Set TEST_DATABASE_URL to the PostgreSQL URL for maxvpn_test"
        )

    try:
        url = make_url(value)
    except (ArgumentError, ValueError):
        raise pytest.UsageError("Invalid TEST_DATABASE_URL format") from None

    if (
        url.get_backend_name() != "postgresql"
        or url.database != TEST_DATABASE_NAME
        or "dbname" in url.query
    ):
        raise pytest.UsageError(
            "TEST_DATABASE_URL must target PostgreSQL maxvpn_test "
            "without a dbname override"
        )

    return url


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(_test_database_url())

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
    database = session.execute(text("SELECT current_database()")).scalar_one()
    if database != TEST_DATABASE_NAME:
        raise RuntimeError("Refusing to truncate tables outside maxvpn_test")

    table_names = ", ".join(
        table.name for table in reversed(Base.metadata.sorted_tables)
    )

    session.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
    session.commit()


@pytest.fixture
def db_session(session_factory) -> Generator[Session, None, None]:
    with session_factory() as session:
        truncate_all_tables(session)
        try:
            yield session
        finally:
            session.rollback()
