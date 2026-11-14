from __future__ import annotations

from abc import ABC, abstractmethod

from backend.models.server import Server


class ServerRepository(ABC):
    """
    Port for accessing VPN servers.
    """

    @abstractmethod
    def get_all(self) -> list[Server]:
        """
        Return all servers.
        """
        raise NotImplementedError

    @abstractmethod
    def get_available(self) -> list[Server]:
        """
        Return only available servers.
        """
        raise NotImplementedError

    @abstractmethod
    def update(self, server: Server) -> None:
        """
        Persist changes to a VPN server.
        """
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, server_id: int) -> Server | None:
        """
        Find a VPN server by ID.
        """
        raise NotImplementedError
