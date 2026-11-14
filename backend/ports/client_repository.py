from __future__ import annotations

from abc import ABC, abstractmethod

from backend.models.client import Client


class ClientRepository(ABC):
    """
    Port for accessing VPN clients.
    """

    @abstractmethod
    def get_used_addresses(self) -> set[str]:
        """
        Return addresses already assigned to clients.
        """
        raise NotImplementedError

    @abstractmethod
    def add(self, client: Client) -> None:
        """
        Persist a client.
        """
        raise NotImplementedError

    @abstractmethod
    def get_by_name(self, name: str) -> Client | None:
        """
        Find a client by name.
        """
        raise NotImplementedError

    @abstractmethod
    def delete(self, client: Client) -> None:
        """
        Delete a client.
        """
        raise NotImplementedError

    @abstractmethod
    def get_by_server_id(self, server_id: int) -> list[Client]:
        """
        Return clients registered on the specified VPN server.
        """
        raise NotImplementedError
