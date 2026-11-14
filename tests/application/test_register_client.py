from unittest.mock import Mock

import pytest

from backend.application.use_cases.register_client import (
    RegisterClientUseCase,
)
from backend.models.client_config import ClientConfig
from backend.models.key_pair import KeyPair
from backend.models.peer import Peer
from backend.models.server import Server
from backend.models.tunnel import Tunnel


def make_config() -> ClientConfig:
    server = Server(
        id=1,
        name="Warsaw-1",
        country="PL",
        city="Warsaw",
        endpoint="pl1.maxvpn.local:51820",
        public_key="server-public-key",
    )

    return ClientConfig(
        server=server,
        key_pair=KeyPair(
            private_key="client-private-key",
            public_key="client-public-key",
        ),
        tunnel=Tunnel(
            address="10.100.0.2/32",
        ),
        peer=Peer(
            public_key="server-public-key",
            allowed_ips="0.0.0.0/0",
        ),
    )


def make_use_case():
    unit_of_work = Mock()
    unit_of_work.clients = Mock()

    peer_manager = Mock()

    use_case = RegisterClientUseCase(
        unit_of_work=unit_of_work,
        peer_manager=peer_manager,
    )

    return use_case, unit_of_work, peer_manager


def test_register_client_persists_client_and_adds_peer():
    use_case, unit_of_work, peer_manager = make_use_case()

    client = use_case.execute(
        config=make_config(),
        name="phone",
    )

    assert client.name == "phone"
    assert client.server_id == 1
    assert client.public_key == "client-public-key"
    assert client.address == "10.100.0.2/32"
    assert client.enabled is True

    unit_of_work.clients.add.assert_called_once_with(client)

    peer_manager.add_peer.assert_called_once_with(
        public_key="client-public-key",
        address="10.100.0.2",
    )

    unit_of_work.commit.assert_called_once()
    unit_of_work.rollback.assert_not_called()


def test_register_client_rolls_back_when_peer_registration_fails():
    use_case, unit_of_work, peer_manager = make_use_case()

    peer_manager.add_peer.side_effect = RuntimeError("wg failed")

    with pytest.raises(RuntimeError, match="wg failed"):
        use_case.execute(
            config=make_config(),
            name="phone",
        )

    unit_of_work.clients.add.assert_called_once()
    unit_of_work.rollback.assert_called_once()
    unit_of_work.commit.assert_not_called()
    peer_manager.remove_peer.assert_not_called()


def test_register_client_removes_peer_when_commit_fails():
    use_case, unit_of_work, peer_manager = make_use_case()

    unit_of_work.commit.side_effect = RuntimeError("database failed")

    with pytest.raises(RuntimeError, match="database failed"):
        use_case.execute(
            config=make_config(),
            name="phone",
        )

    unit_of_work.clients.add.assert_called_once()
    unit_of_work.rollback.assert_called_once()

    peer_manager.add_peer.assert_called_once_with(
        public_key="client-public-key",
        address="10.100.0.2",
    )

    peer_manager.remove_peer.assert_called_once_with(
        public_key="client-public-key",
    )
