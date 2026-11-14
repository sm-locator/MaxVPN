from __future__ import annotations

from backend.infrastructure.database.repositories.sqlalchemy_client_repository import (
    SqlAlchemyClientRepository,
)
from backend.infrastructure.database.repositories.sqlalchemy_server_repository import (
    SqlAlchemyServerRepository,
)
from backend.ports.unit_of_work import UnitOfWork
from sqlalchemy.orm import Session


class SqlAlchemyUnitOfWork(UnitOfWork):
    """
    SQLAlchemy implementation of the application transaction boundary.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

        self.clients = SqlAlchemyClientRepository(session)
        self.servers = SqlAlchemyServerRepository(session)

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
