from __future__ import annotations

from backend.models.client import Client
from backend.models.client_config import ClientConfig
from backend.ports.unit_of_work import UnitOfWork
from backend.ports.wireguard_peer_manager import WireGuardPeerManager


class RegisterClientUseCase:
    """
    Registers a generated VPN client in persistent storage
    and on the WireGuard server.
    """

    def __init__(
        self,
        unit_of_work: UnitOfWork,
        peer_manager: WireGuardPeerManager,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._peer_manager = peer_manager

    def execute(
        self,
        config: ClientConfig,
        name: str,
        description: str | None = None,
    ) -> Client:
        client = Client(
            id=None,
            name=name,
            server_id=config.server.id,
            private_key=config.key_pair.private_key,
            public_key=config.key_pair.public_key,
            address=config.tunnel.address,
            description=description,
        )

        self._unit_of_work.clients.add(client)

        peer_added = False

        try:
            self._peer_manager.add_peer(
                public_key=client.public_key,
                address=client.address.removesuffix("/32"),
            )
            peer_added = True

            self._unit_of_work.commit()

            return client

        except Exception:
            self._unit_of_work.rollback()

            if peer_added:
                try:
                    self._peer_manager.remove_peer(
                        public_key=client.public_key,
                    )
                except Exception:
                    pass

            raise
