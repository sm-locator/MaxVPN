from __future__ import annotations

from pathlib import Path

from backend.models.client_config import ClientConfig
from backend.models.key_pair import KeyPair
from backend.models.peer import Peer
from backend.models.tunnel import Tunnel
from backend.ports.config_renderer import ConfigRenderer
from backend.ports.unit_of_work import UnitOfWork


class ExportExistingClientConfigUseCase:
    """
    Rebuilds and exports the configuration of an existing VPN client.
    """

    def __init__(
        self,
        unit_of_work: UnitOfWork,
        renderer: ConfigRenderer,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._renderer = renderer

    def execute(
        self,
        client_name: str,
        destination: Path,
    ) -> Path:
        client = self._unit_of_work.clients.get_by_name(client_name)

        if client is None:
            raise ValueError(f"Client '{client_name}' does not exist.")

        server = self._unit_of_work.servers.get_by_id(client.server_id)

        if server is None:
            raise ValueError(f"Server with id {client.server_id} does not exist.")

        config = ClientConfig(
            server=server,
            key_pair=KeyPair(
                private_key=client.private_key,
                public_key=client.public_key,
            ),
            tunnel=Tunnel(
                address=client.address,
            ),
            peer=Peer(
                public_key=server.public_key,
                allowed_ips="0.0.0.0/0",
            ),
        )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination.write_text(
            self._renderer.render(config),
            encoding="utf-8",
        )

        return destination
