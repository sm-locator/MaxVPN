from tests.unit.vpn.helpers import (
    create_client,
    create_dependencies,
    create_manager,
    create_server,
)


def test_get_client_config_returns_config() -> None:
    deps = create_dependencies()

    client = create_client()

    deps.repository.get_by_name.return_value = client
    deps.config_generator.generate.return_value = "client_config"

    manager = create_manager(deps)

    server = create_server()

    result = manager.get_client_config(
        client_name="phone",
        server=server,
    )

    assert result == "client_config"


def test_list_clients_returns_repository_clients() -> None:
    deps = create_dependencies()

    manager = create_manager(deps)

    clients = [create_client()]

    deps.repository.list_clients.return_value = clients

    result = manager.list_clients()

    assert result == clients
    deps.repository.list_clients.assert_called_once_with()


def test_get_client_returns_repository_client() -> None:
    deps = create_dependencies()

    client = create_client()

    deps.repository.get_by_name.return_value = client

    manager = create_manager(deps)

    result = manager.get_client("phone")

    assert result == client
    deps.repository.get_by_name.assert_called_once_with("phone")
