from unittest.mock import Mock

import pytest

from app.vpn.exceptions import ClientNotFoundError
from tests.unit.vpn.helpers import (
    create_client,
    create_dependencies,
    create_manager,
)


def test_delete_client() -> None:
    deps = create_dependencies()

    manager = create_manager(deps)

    client = Mock()

    deps.repository.get_by_name.return_value = client

    manager.delete_client("phone")

    deps.repository.get_by_name.assert_called_once_with("phone")
    deps.repository.delete.assert_called_once_with(client)


def test_delete_unknown_client_raises_error() -> None:
    deps = create_dependencies()

    deps.repository.get_by_name.return_value = None

    manager = create_manager(deps)

    with pytest.raises(ClientNotFoundError):
        manager.delete_client("phone")

    deps.repository.delete.assert_not_called()


def test_delete_client_removes_peer_before_deleting_repository() -> None:
    deps = create_dependencies()

    client = create_client()
    deps.repository.get_by_name.return_value = client

    manager = create_manager(deps)

    manager.delete_client("phone")

    deps.peer_manager.remove_peer.assert_called_once_with("public_key")
    deps.repository.delete.assert_called_once_with(client)
