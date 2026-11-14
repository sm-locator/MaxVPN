from __future__ import annotations

from backend.models.server import Server


class InMemoryServerRepository:
    """
    Temporary in-memory repository.

    Later it will be replaced with SQLAlchemy.
    """

    def __init__(self, servers: list[Server]):
        self._servers = servers

    def get_all(self) -> list[Server]:
        return list(self._servers)

    def get_available(self) -> list[Server]:
        return [server for server in self._servers if server.online]
