from ipaddress import IPv4Address
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.api.dependencies import get_wireguard_manager
from app.main import app
from app.vpn.wireguard.client import CreatedWireGuardClient
from app.vpn.wireguard.manager import WireGuardManager
from app.vpn.wireguard.server_settings import WireGuardServerSettings

client = TestClient(app)


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
                server_public_key="server_public_key",
                endpoint="vpn.example.com:51820",
                dns="1.1.1.1",
                allowed_ips="0.0.0.0/0",
                persistent_keepalive=25,
            ),
        )

    finally:
        app.dependency_overrides.clear()
