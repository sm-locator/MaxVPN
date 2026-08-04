from tests.unit.vpn.helpers import (
    create_client,
    create_dependencies,
    create_manager,
)


def test_update_client_updates_repository() -> None:
    deps = create_dependencies()

    client = create_client()

    deps.repository.get_by_name.return_value = client

    manager = create_manager(deps)

    manager.update_client(
        client_name="phone",
        name="iphone",
        description="My iPhone",
        enabled=False,
    )

    deps.repository.get_by_name.assert_called_once_with("phone")

    deps.repository.update.assert_called_once_with(
        client_name="phone",
        client=client,
    )

    assert client.name == "iphone"
    assert client.description == "My iPhone"
    assert client.enabled is False
