from __future__ import annotations

from backend.infrastructure.database.repositories.sqlalchemy_client_repository import (
    SqlAlchemyClientRepository,
)
from backend.ports.unit_of_work import UnitOfWork
from sqlalchemy.orm import Session


class DryRunUnitOfWork(UnitOfWork):
    """
    SQLAlchemy unit of work that never commits changes.

    Changes may be flushed to obtain generated IDs, but the transaction
    remains uncommitted and can be rolled back by the caller.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self.clients = SqlAlchemyClientRepository(session)

    def commit(self) -> None:
        """
        Keep the transaction open during dry-run.
        """
        self._session.flush()

    def rollback(self) -> None:
        self._session.rollback()
