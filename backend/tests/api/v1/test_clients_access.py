from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.api.dependencies import (
    get_export_facade,
    get_wireguard_manager,
    get_wireguard_server_settings,
)
from app.core.config import settings
from app.core.security import create_user_access_token
from app.database.dependencies import get_db
from app.main import app
from app.models.roles import UserRole
from app.models.user import User

OPERATIONS = [
    ("POST", "", {"client_name": "secret-peer"}),
    ("GET", "", None),
    ("GET", "/secret-peer", None),
    ("PUT", "/secret-peer", {"name": "renamed", "enabled": False}),
    ("DELETE", "/secret-peer", None),
    ("POST", "/secret-peer/enable", None),
    ("POST", "/secret-peer/disable", None),
    ("GET", "/secret-peer/config", None),
    ("GET", "/secret-peer/qr", None),
]


@pytest.mark.parametrize("method,path,body", OPERATIONS)
@pytest.mark.parametrize("identity", ["anonymous", "invalid", "expired", "user"])
def test_denied_clients_access_never_reads_or_changes_peers(
    method, path, body, identity
):
    # Use the real bearer-token and role checks; only persistence and VPN
    # dependencies are replaced. A rejected request must not even build them.
    db = Mock()
    db.scalar.return_value = User(
        id=42, email="user@example.test", password_hash="hash", role=UserRole.USER
    )
    factories = [Mock() for _ in range(3)]
    app.dependency_overrides.update(
        {
            get_db: lambda: db,
            get_wireguard_manager: lambda: factories[0](),
            get_wireguard_server_settings: lambda: factories[1](),
            get_export_facade: lambda: factories[2](),
        }
    )
    headers = {}
    if identity != "anonymous":
        token = {
            "invalid": "invalid-token",
            "expired": jwt.encode(
                {"sub": "user@example.test", "exp": 1},
                settings.SECRET_KEY,
                algorithm=settings.ALGORITHM,
            ),
            "user": create_user_access_token(db.scalar.return_value),
        }[identity]
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = TestClient(app).request(
            method, f"/api/v1/clients{path}", json=body, headers=headers
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == (403 if identity == "user" else 401)
    expected_detail = {
        "anonymous": "Not authenticated",
        "invalid": "Invalid authentication credentials",
        "expired": "Invalid authentication credentials",
        "user": "Insufficient permissions",
    }[identity]
    assert response.json() == {"detail": expected_detail}
    assert response.headers["content-type"] == "application/json"
    assert "content-disposition" not in response.headers
    for factory in factories:
        factory.assert_not_called()
    if identity == "user":
        db.scalar.assert_called_once()
    else:
        db.scalar.assert_not_called()
