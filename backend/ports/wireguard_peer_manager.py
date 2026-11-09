from __future__ import annotations

from abc import ABC, abstractmethod


class WireGuardPeerManager(ABC):
    """
    Port for managing WireGuard peers on a VPN server.
    """

    @abstractmethod
    def add_peer(
        self,
        public_key: str,
        address: str,
    ) -> None:
        """
        Add a WireGuard peer to the server.
        """
        raise NotImplementedError

    @abstractmethod
    def remove_peer(
        self,
        public_key: str,
    ) -> None:
        """
        Remove a WireGuard peer from the server.
        """
        raise NotImplementedError
