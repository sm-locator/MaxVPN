from ipaddress import IPv4Address
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_wireguard_manager
from app.auth.dependencies import get_current_user
from app.main import app
from app.models.roles import UserRole
from app.models.user import User
from app.vpn.exceptions import ClientNotFoundError
from app.vpn.models import WireGuardClient
from app.vpn.wireguard.client import CreatedWireGuardClient
from app.vpn.wireguard.manager import WireGuardManager
from app.vpn.wireguard.server_settings import WireGuardServerSettings

client = TestClient(app)


@pytest.fixture(autouse=True)
def authenticated_admin():
    app.dependency_overrides[get_current_user] = lambda: User(
        id=1, email="admin@example.test", password_hash="hash", role=UserRole.ADMIN
    )
    yield
    app.dependency_overrides.clear()


def test_create_client_returns_201():
    manager = Mock(spec=WireGuardManager)

    manager.create_client.return_value = CreatedWireGuardClient(
        name="phone",
        ip_address=IPv4Address("10.8.0.2"),
        public_key="public_key",
        config="client_config",
    )

    app.dependency_overrides[get_wireguard_manager] = lambda: manager

    try:
        response = client.post(
            "/api/v1/clients",
            json={
                "client_name": "phone",
            },
        )

        assert response.status_code == 201

        assert response.json() == {
            "name": "phone",
            "ip_address": "10.8.0.2",
            "public_key": "public_key",
            "config": "client_config",
        }

        manager.create_client.assert_called_once_with(
            client_name="phone",
            server=WireGuardServerSettings(
                server_public_key="<публичный ключ сервера>",
                endpoint="<домен или IP>:51820",
                dns="1.1.1.1",
                allowed_ips="0.0.0.0/0",
                persistent_keepalive=25,
            ),
        )

    finally:
        app.dependency_overrides.clear()


def test_delete_client_returns_204() -> None:
    manager = Mock(spec=WireGuardManager)

    app.dependency_overrides[get_wireguard_manager] = lambda: manager

    try:
        response = client.delete("/api/v1/clients/phone")

        assert response.status_code == 204
        assert response.content == b""

        manager.delete_client.assert_called_once_with("phone")

    finally:
        app.dependency_overrides.clear()


def test_delete_unknown_client_returns_404() -> None:
    manager = Mock(spec=WireGuardManager)
    manager.delete_client.side_effect = ClientNotFoundError(
        "WireGuard client 'phone' not found."
    )

    app.dependency_overrides[get_wireguard_manager] = lambda: manager

    try:
        response = client.delete("/api/v1/clients/phone")

        assert response.status_code == 404
        assert response.json() == {"detail": "WireGuard client 'phone' not found."}

        manager.delete_client.assert_called_once_with("phone")

    finally:
        app.dependency_overrides.clear()


def test_get_client_config_returns_200():
    manager = Mock(spec=WireGuardManager)

    manager.get_client_config.return_value = "client_config"

    app.dependency_overrides[get_wireguard_manager] = lambda: manager

    try:
        response = client.get("/api/v1/clients/phone/config")

        assert response.status_code == 200
        assert response.text == "client_config"
        assert response.headers["content-type"].startswith("text/plain")

        manager.get_client_config.assert_called_once_with(
            client_name="phone",
            server=WireGuardServerSettings(
                server_public_key="<публичный ключ сервера>",
                endpoint="<домен или IP>:51820",
                dns="1.1.1.1",
                allowed_ips="0.0.0.0/0",
                persistent_keepalive=25,
            ),
        )

    finally:
        app.dependency_overrides.clear()


def test_list_clients_returns_200() -> None:
    manager = Mock(spec=WireGuardManager)

    manager.list_clients.return_value = [
        WireGuardClient(
            name="phone",
            private_key="private_key_1",
            public_key="public_key_1",
            ip_address=IPv4Address("10.8.0.2"),
        ),
        WireGuardClient(
            name="laptop",
            private_key="private_key_2",
            public_key="public_key_2",
            ip_address=IPv4Address("10.8.0.3"),
        ),
    ]

    app.dependency_overrides[get_wireguard_manager] = lambda: manager

    try:
        response = client.get("/api/v1/clients")

        assert response.status_code == 200
        assert response.json() == [
            {
                "name": "phone",
                "ip_address": "10.8.0.2",
                "public_key": "public_key_1",
                "description": None,
                "enabled": True,
            },
            {
                "name": "laptop",
                "ip_address": "10.8.0.3",
                "public_key": "public_key_2",
                "description": None,
                "enabled": True,
            },
        ]

        manager.list_clients.assert_called_once_with()

    finally:
        app.dependency_overrides.clear()


def test_update_client_returns_200() -> None:
    manager = Mock(spec=WireGuardManager)

    updated_client = WireGuardClient(
        name="iphone",
        private_key="private_key",
        public_key="public_key",
        ip_address=IPv4Address("10.8.0.2"),
        description="My iPhone",
        enabled=True,
    )

    manager.update_client.return_value = updated_client

    app.dependency_overrides[get_wireguard_manager] = lambda: manager

    try:
        response = client.put(
            "/api/v1/clients/phone",
            json={
                "name": "iphone",
                "description": "My iPhone",
                "enabled": True,
            },
        )

        assert response.status_code == 200

        assert response.json() == {
            "name": "iphone",
            "ip_address": "10.8.0.2",
            "public_key": "public_key",
            "description": "My iPhone",
            "enabled": True,
        }

        manager.update_client.assert_called_once_with(
            client_name="phone",
            name="iphone",
            description="My iPhone",
            enabled=True,
        )

    finally:
        app.dependency_overrides.clear()


def test_get_client_returns_200() -> None:
    manager = Mock(spec=WireGuardManager)

    manager.get_client.return_value = WireGuardClient(
        name="phone",
        private_key="private_key",
        public_key="public_key",
        ip_address=IPv4Address("10.8.0.2"),
        description="My phone",
        enabled=True,
    )

    app.dependency_overrides[get_wireguard_manager] = lambda: manager

    try:
        response = client.get("/api/v1/clients/phone")

        assert response.status_code == 200
        assert response.json() == {
            "name": "phone",
            "ip_address": "10.8.0.2",
            "public_key": "public_key",
            "description": "My phone",
            "enabled": True,
        }

        manager.get_client.assert_called_once_with("phone")

    finally:
        app.dependency_overrides.clear()


def test_get_unknown_client_returns_404() -> None:
    manager = Mock(spec=WireGuardManager)

    manager.get_client.side_effect = ClientNotFoundError(
        "WireGuard client 'phone' not found."
    )

    app.dependency_overrides[get_wireguard_manager] = lambda: manager

    try:
        response = client.get("/api/v1/clients/phone")

        assert response.status_code == 404
        assert response.json() == {"detail": "WireGuard client 'phone' not found."}

        manager.get_client.assert_called_once_with("phone")

    finally:
        app.dependency_overrides.clear()


def test_disable_client_returns_204() -> None:
    manager = Mock(spec=WireGuardManager)

    app.dependency_overrides[get_wireguard_manager] = lambda: manager

    try:
        response = client.post("/api/v1/clients/phone/disable")

        assert response.status_code == 204
        assert response.content == b""

        manager.disable_client.assert_called_once_with("phone")

    finally:
        app.dependency_overrides.clear()


def test_enable_client_returns_204() -> None:
    manager = Mock(spec=WireGuardManager)

    app.dependency_overrides[get_wireguard_manager] = lambda: manager

    try:
        response = client.post("/api/v1/clients/phone/enable")

        assert response.status_code == 204
        assert response.content == b""

        manager.enable_client.assert_called_once_with("phone")

    finally:
        app.dependency_overrides.clear()


def test_download_client_config_returns_file() -> None:
    manager = Mock(spec=WireGuardManager)

    manager.get_client_config.return_value = "[Interface]\nPrivateKey = private_key\n"

    app.dependency_overrides[get_wireguard_manager] = lambda: manager

    try:
        response = client.get("/api/v1/clients/phone/config")

        assert response.status_code == 200
        assert response.text == ("[Interface]\nPrivateKey = private_key\n")

        assert (
            response.headers["content-disposition"]
            == 'attachment; filename="phone.conf"'
        )

        assert response.headers["content-type"].startswith("text/plain")

        manager.get_client_config.assert_called_once()

    finally:
        app.dependency_overrides.clear()


def test_download_client_qr_returns_png() -> None:
    manager = Mock(spec=WireGuardManager)

    manager.get_client_config.return_value = "[Interface]\nPrivateKey = private_key\n"

    app.dependency_overrides[get_wireguard_manager] = lambda: manager

    try:
        response = client.get("/api/v1/clients/phone/qr")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content.startswith(b"\x89PNG")

        manager.get_client_config.assert_called_once()

    finally:
        app.dependency_overrides.clear()
