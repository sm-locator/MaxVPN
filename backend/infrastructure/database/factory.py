from backend.infrastructure.database.repositories.sqlalchemy_client_repository import (
    SqlAlchemyClientRepository,
)
from backend.infrastructure.database.repositories.sqlalchemy_server_repository import (
    SqlAlchemyServerRepository,
)
from backend.infrastructure.database.session import SessionFactory
from sqlalchemy.orm import Session


def create_session() -> Session:
    """
    Create a SQLAlchemy session.
    """
    return SessionFactory()


def create_server_repository(
    session: Session | None = None,
) -> SqlAlchemyServerRepository:
    """
    Create a SQLAlchemy server repository.
    """
    return SqlAlchemyServerRepository(
        session or create_session(),
    )


def create_client_repository(
    session: Session | None = None,
) -> SqlAlchemyClientRepository:
    """
    Create a SQLAlchemy client repository.
    """
    return SqlAlchemyClientRepository(
        session or create_session(),
    )
