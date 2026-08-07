from __future__ import annotations

from backend.models.server import Server


class ServerRepository:
    """
    Temporary in-memory repository.

    Later it will be replaced with SQLAlchemy.
    """

    def __init__(self, servers: list[Server]):
        self._servers = servers

    def all(self) -> list[Server]:
        return list(self._servers)

    def online(self) -> list[Server]:
        return [server for server in self._servers if server.online]
