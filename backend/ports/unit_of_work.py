from __future__ import annotations

from abc import ABC, abstractmethod

from backend.ports.client_repository import ClientRepository
from backend.ports.server_repository import ServerRepository


class UnitOfWork(ABC):
    """
    Transaction boundary for application operations.
    """

    clients: ClientRepository
    servers: ServerRepository

    @abstractmethod
    def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        raise NotImplementedError
