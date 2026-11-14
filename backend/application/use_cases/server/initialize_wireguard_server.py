from __future__ import annotations

from backend.infrastructure.config.settings import Settings
from backend.models.server import Server
from backend.ports.unit_of_work import UnitOfWork
from backend.ports.wireguard_peer_manager import WireGuardPeerManager
from backend.ports.wireguard_server_key_store import WireGuardServerKeyStore
from backend.ports.wireguard_server_manager import WireGuardServerManager


class InitializeWireGuardServerUseCase:
    """
    Initializes and activates the WireGuard server interface.
    """

    def __init__(
        self,
        server_manager: WireGuardServerManager,
        server_key_store: WireGuardServerKeyStore,
        peer_manager: WireGuardPeerManager,
        unit_of_work: UnitOfWork,
        settings: Settings,
    ) -> None:
        self._server_manager = server_manager
        self._server_key_store = server_key_store
        self._peer_manager = peer_manager
        self._unit_of_work = unit_of_work
        self._settings = settings

    def execute(self, server_id: int) -> Server:
        server = self._unit_of_work.servers.get_by_id(server_id)

        if server is None:
            raise ValueError(f"Server with id {server_id} does not exist.")

        if self._server_key_store.exists():
            private_key = self._server_key_store.read()
        else:
            private_key = self._server_manager.generate_private_key()
            self._server_key_store.write(private_key)

        self._server_manager.ensure_interface()

        self._server_manager.configure(
            private_key=private_key,
            listen_port=self._settings.wireguard_listen_port,
        )

        self._server_manager.configure_address(
            self._settings.wireguard_server_address,
        )

        self._server_manager.set_up()

        # Restore all active clients belonging to this server.
        clients = self._unit_of_work.clients.get_by_server_id(server_id)

        for client in clients:
            self._peer_manager.add_peer(
                public_key=client.public_key,
                address=client.address.removesuffix("/32"),
            )

        public_key = self._server_manager.get_public_key()

        server.public_key = public_key

        self._unit_of_work.servers.update(server)
        self._unit_of_work.commit()

        return server
