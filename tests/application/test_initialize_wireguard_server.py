from unittest.mock import Mock

from backend.application.use_cases.server.initialize_wireguard_server import (
    InitializeWireGuardServerUseCase,
)
from backend.infrastructure.config.settings import Settings
from backend.models.server import Server

SERVER_PRIVATE_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
SERVER_PUBLIC_KEY = "REAL-SERVER-PUBLIC-KEY"


def make_server() -> Server:
    return Server(
        id=1,
        name="Warsaw-1",
        country="PL",
        city="Warsaw",
        endpoint="pl1.maxvpn.local:51820",
        public_key="old-public-key",
    )


def make_settings() -> Settings:
    return Settings(
        wireguard_server_address="10.100.0.1/24",
        wireguard_listen_port=51820,
    )


def test_initialize_wireguard_server_generates_and_persists_private_key():
    manager = Mock()
    key_store = Mock()
    unit_of_work = Mock()
    peer_manager = Mock()

    server = make_server()

    unit_of_work.servers.get_by_id.return_value = server
    unit_of_work.clients.get_by_server_id.return_value = []
    key_store.exists.return_value = False
    manager.generate_private_key.return_value = SERVER_PRIVATE_KEY
    manager.get_public_key.return_value = SERVER_PUBLIC_KEY

    use_case = InitializeWireGuardServerUseCase(
        server_manager=manager,
        server_key_store=key_store,
        unit_of_work=unit_of_work,
        peer_manager=peer_manager,
        settings=make_settings(),
    )

    result = use_case.execute(server_id=1)

    assert result is server
    assert server.public_key == SERVER_PUBLIC_KEY

    unit_of_work.clients.get_by_server_id.assert_called_once_with(1)
    peer_manager.add_peer.assert_not_called()

    unit_of_work.servers.get_by_id.assert_called_once_with(1)

    key_store.exists.assert_called_once_with()
    manager.generate_private_key.assert_called_once_with()
    key_store.write.assert_called_once_with(SERVER_PRIVATE_KEY)

    manager.ensure_interface.assert_called_once_with()
    manager.configure.assert_called_once_with(
        private_key=SERVER_PRIVATE_KEY,
        listen_port=51820,
    )
    manager.configure_address.assert_called_once_with(
        "10.100.0.1/24",
    )
    manager.set_up.assert_called_once_with()
    manager.get_public_key.assert_called_once_with()

    unit_of_work.servers.update.assert_called_once_with(server)
    unit_of_work.commit.assert_called_once_with()


def test_initialize_wireguard_server_reuses_existing_private_key():
    manager = Mock()
    key_store = Mock()
    unit_of_work = Mock()
    peer_manager = Mock()

    server = make_server()

    unit_of_work.servers.get_by_id.return_value = server
    unit_of_work.clients.get_by_server_id.return_value = []
    key_store.exists.return_value = True
    key_store.read.return_value = SERVER_PRIVATE_KEY
    manager.get_public_key.return_value = SERVER_PUBLIC_KEY

    use_case = InitializeWireGuardServerUseCase(
        server_manager=manager,
        server_key_store=key_store,
        unit_of_work=unit_of_work,
        peer_manager=peer_manager,
        settings=make_settings(),
    )

    result = use_case.execute(server_id=1)

    assert result is server
    assert server.public_key == SERVER_PUBLIC_KEY

    unit_of_work.clients.get_by_server_id.assert_called_once_with(1)
    peer_manager.add_peer.assert_not_called()

    key_store.exists.assert_called_once_with()
    key_store.read.assert_called_once_with()
    manager.generate_private_key.assert_not_called()
    key_store.write.assert_not_called()

    manager.configure.assert_called_once_with(
        private_key=SERVER_PRIVATE_KEY,
        listen_port=51820,
    )


def test_initialize_wireguard_server_rejects_unknown_server():
    manager = Mock()
    key_store = Mock()
    unit_of_work = Mock()
    peer_manager = Mock()

    unit_of_work.servers.get_by_id.return_value = None

    use_case = InitializeWireGuardServerUseCase(
        server_manager=manager,
        server_key_store=key_store,
        unit_of_work=unit_of_work,
        peer_manager=peer_manager,
        settings=make_settings(),
    )

    try:
        use_case.execute(server_id=999)
    except ValueError as exc:
        assert str(exc) == "Server with id 999 does not exist."
    else:
        raise AssertionError("Expected ValueError")

    unit_of_work.servers.get_by_id.assert_called_once_with(999)

    key_store.exists.assert_not_called()
    key_store.read.assert_not_called()
    key_store.write.assert_not_called()

    manager.generate_private_key.assert_not_called()
    manager.ensure_interface.assert_not_called()
    manager.configure.assert_not_called()
    manager.configure_address.assert_not_called()
    manager.set_up.assert_not_called()
    manager.get_public_key.assert_not_called()

    unit_of_work.servers.update.assert_not_called()
    unit_of_work.commit.assert_not_called()
