from __future__ import annotations

from backend.ports.wireguard_peer_manager import WireGuardPeerManager


class DryRunWireGuardPeerManager(WireGuardPeerManager):
    """
    WireGuard peer manager that performs no system changes.

    Intended for CLI dry-run and integration testing.
    """

    def __init__(self) -> None:
        self.added_peers: list[tuple[str, str]] = []
        self.removed_peers: list[str] = []

    def add_peer(
        self,
        public_key: str,
        address: str,
    ) -> None:
        self.added_peers.append(
            (public_key, address),
        )

    def remove_peer(
        self,
        public_key: str,
    ) -> None:
        self.removed_peers.append(public_key)
