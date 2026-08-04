from ipaddress import IPv4Address

import pytest

from app.vpn.exceptions import ClientNotFoundError
from tests.unit.vpn.helpers import (
    create_client,
    create_dependencies,
    create_manager,
)


def test_disable_client_updates_repository() -> None:
    deps = create_dependencies()

    client = create_client(enabled=True)
    deps.repository.get_by_name.return_value = client

    manager = create_manager(deps)

    manager.disable_client("phone")

    assert client.enabled is False

    deps.repository.update.assert_called_once_with(
        client_name="phone",
        client=client,
    )


def test_disable_client_removes_peer() -> None:
    deps = create_dependencies()

    client = create_client()
    deps.repository.get_by_name.return_value = client

    manager = create_manager(deps)

    manager.disable_client("phone")

    deps.peer_manager.remove_peer.assert_called_once_with("public_key")


def test_enable_client_adds_peer() -> None:
    deps = create_dependencies()

    client = create_client()
    deps.repository.get_by_name.return_value = client

    manager = create_manager(deps)

    manager.enable_client("phone")

    deps.peer_manager.add_peer.assert_called_once_with(
        public_key="public_key",
        address=IPv4Address("10.8.0.2"),
    )


def test_enable_client_updates_repository() -> None:
    deps = create_dependencies()

    client = create_client(enabled=False)
    deps.repository.get_by_name.return_value = client

    manager = create_manager(deps)

    manager.enable_client("phone")

    assert client.enabled is True

    deps.repository.update.assert_called_once_with(
        client_name="phone",
        client=client,
    )


def test_enable_unknown_client_raises_error() -> None:
    deps = create_dependencies()

    deps.repository.get_by_name.return_value = None

    manager = create_manager(deps)

    with pytest.raises(ClientNotFoundError):
        manager.enable_client("phone")

    deps.peer_manager.add_peer.assert_not_called()
    deps.repository.update.assert_not_called()


def test_enable_client_does_not_update_repository_when_add_peer_fails() -> None:
    deps = create_dependencies()

    client = create_client(enabled=False)

    deps.repository.get_by_name.return_value = client

    deps.peer_manager.add_peer.side_effect = RuntimeError("wg failed")

    manager = create_manager(deps)

    with pytest.raises(RuntimeError, match="wg failed"):
        manager.enable_client("phone")

    assert client.enabled is False
    deps.repository.update.assert_not_called()
