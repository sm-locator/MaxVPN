from __future__ import annotations

from abc import ABC, abstractmethod


class WireGuardServerManager(ABC):
    """
    Port for managing the WireGuard server interface.
    """

    @abstractmethod
    def interface_exists(self) -> bool:
        """
        Return True when the WireGuard interface exists.
        """
        raise NotImplementedError

    @abstractmethod
    def ensure_interface(self) -> None:
        """
        Create the WireGuard interface when it does not exist.
        """
        raise NotImplementedError

    @abstractmethod
    def configure(
        self,
        private_key: str,
        listen_port: int,
    ) -> None:
        """
        Configure the server private key and listen port.
        """
        raise NotImplementedError

    @abstractmethod
    def configure_address(self, address: str) -> None:
        """
        Assign the VPN address to the WireGuard interface.
        """
        raise NotImplementedError

    @abstractmethod
    def set_up(self) -> None:
        """
        Bring the WireGuard interface up.
        """
        raise NotImplementedError

    @abstractmethod
    def set_down(self) -> None:
        """
        Bring the WireGuard interface down.
        """
        raise NotImplementedError

    @abstractmethod
    def is_up(self) -> bool:
        """
        Return True when the WireGuard interface is operational.
        """
        raise NotImplementedError

    @abstractmethod
    def get_public_key(self) -> str:
        """
        Return the public key of the WireGuard server interface.
        """
        raise NotImplementedError

    @abstractmethod
    def remove_interface(self) -> None:
        """
        Remove the WireGuard interface.
        """
        raise NotImplementedError

    @abstractmethod
    def generate_private_key(self) -> str:
        """
        Generate a new WireGuard private key.
        """
        raise NotImplementedError
