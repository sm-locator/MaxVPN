from __future__ import annotations

import subprocess

from backend.ports.wireguard_peer_manager import WireGuardPeerManager


class SystemWireGuardPeerManager(WireGuardPeerManager):
    """
    Manages WireGuard peers using the system wg command.
    """

    def __init__(
        self,
        interface_name: str,
        binary: str = "wg",
    ) -> None:
        self._interface_name = interface_name
        self._binary = binary

    def add_peer(
        self,
        public_key: str,
        address: str,
    ) -> None:
        subprocess.run(
            [
                self._binary,
                "set",
                self._interface_name,
                "peer",
                public_key,
                "allowed-ips",
                f"{address}/32",
            ],
            check=True,
        )

    def remove_peer(
        self,
        public_key: str,
    ) -> None:
        subprocess.run(
            [
                self._binary,
                "set",
                self._interface_name,
                "peer",
                public_key,
                "remove",
            ],
            check=True,
        )
