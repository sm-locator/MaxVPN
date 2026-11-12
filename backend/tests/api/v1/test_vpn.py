from datetime import datetime, timezone
from unittest.mock import Mock

from backend.models.amneziawg_runtime_health import (
    AmneziaWGRuntimeHealth,
)
from backend.services.amneziawg_runtime_manager import (
    AmneziaWGRuntimeManagerResult,
)
from backend.services.vpn_profile_service import (
    VpnProfileRead,
    VpnProfileValidationResult,
)
from fastapi.testclient import TestClient

from app.api.v1.vpn import (
    get_vpn_profile_service,
    get_vpn_runtime_service,
)
from app.auth.dependencies import get_current_user
from app.main import app
from app.models.user import User

client = TestClient(app)


def make_user() -> User:
    return User(
        id=42,
        email="vpn-test@example.com",
        password_hash="hash",
        role="admin",
    )


def make_read() -> VpnProfileRead:
    return VpnProfileRead(
        id=7,
        name="Primary VPN",
        enabled=True,
        has_private_key=True,
        has_preshared_key=True,
    )


def test_get_profile_requires_authentication() -> None:
    response = client.get("/api/v1/vpn/profile")

    assert response.status_code == 401


def test_get_runtime_requires_authentication() -> None:
    response = client.get("/api/v1/vpn/runtime")

    assert response.status_code == 401


def test_start_vpn_requires_authentication_before_runtime_changes() -> None:
    service = Mock()
    app.dependency_overrides[get_vpn_runtime_service] = lambda: service

    try:
        response = client.post("/api/v1/vpn/start")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    service.start.assert_not_called()


def test_get_runtime_returns_health() -> None:
    service = Mock()
    service.get_traffic_mode.return_value = "vpn"

    checked_at = datetime(
        2026,
        9,
        2,
        tzinfo=timezone.utc,
    )

    service.handshake_age_seconds.return_value = 0

    service.get_health.return_value = AmneziaWGRuntimeHealth(
        interface_exists=True,
        interface_up=True,
        expected_peer_found=True,
        expected_endpoint=True,
        listen_port=47182,
        latest_handshake=checked_at,
        rx_bytes=123456,
        tx_bytes=654321,
        endpoint_route_ok=True,
        healthy=True,
        reason=None,
        checked_at=checked_at,
    )

    profile_service = Mock()
    profile_service.preflight_apply.return_value = True

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_vpn_runtime_service] = lambda: service
    app.dependency_overrides[get_vpn_profile_service] = lambda: profile_service

    try:
        response = client.get("/api/v1/vpn/runtime")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    body = response.json()

    assert body["interface"] == "WireGuard"
    assert body["healthy"] is True
    assert body["interface_exists"] is True
    assert body["interface_up"] is True
    assert body["traffic_mode"] == "vpn"
    assert body["expected_peer_found"] is True
    assert body["expected_endpoint"] is True
    assert body["endpoint_route_ok"] is True
    assert body["listen_port"] == 47182
    assert body["rx_bytes"] == 123456
    assert body["tx_bytes"] == 654321
    assert body["reason"] is None
    assert body["handshake_age_seconds"] >= 0
    assert body["in_sync"] is True

    assert "private_key" not in body
    assert "preshared_key" not in body
    assert "provider_config" not in body
    assert "encrypted_provider_config" not in body

    service.get_health.assert_called_once_with()


def test_get_runtime_returns_unhealthy_state() -> None:
    service = Mock()
    service.get_traffic_mode.return_value = "wan"

    checked_at = datetime(
        2026,
        9,
        2,
        tzinfo=timezone.utc,
    )

    service.handshake_age_seconds.return_value = None

    service.get_health.return_value = AmneziaWGRuntimeHealth(
        interface_exists=True,
        interface_up=False,
        expected_peer_found=True,
        expected_endpoint=True,
        listen_port=47182,
        latest_handshake=None,
        rx_bytes=0,
        tx_bytes=0,
        endpoint_route_ok=True,
        healthy=False,
        reason="interface_down",
        checked_at=checked_at,
    )

    profile_service = Mock()
    profile_service.preflight_apply.return_value = False

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_vpn_runtime_service] = lambda: service
    app.dependency_overrides[get_vpn_profile_service] = lambda: profile_service

    try:
        response = client.get("/api/v1/vpn/runtime")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    body = response.json()

    assert body["healthy"] is False
    assert body["interface_up"] is False
    assert body["reason"] == "interface_down"
    assert body["handshake_age_seconds"] is None
    assert body["in_sync"] is False


def test_get_profile_returns_sanitized_metadata() -> None:
    service = Mock()
    service.get.return_value = make_read()

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_vpn_profile_service] = lambda: service

    try:
        response = client.get("/api/v1/vpn/profile")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "id": 7,
        "name": "Primary VPN",
        "enabled": True,
        "has_private_key": True,
        "has_preshared_key": True,
    }

    body = response.json()

    assert "private_key" not in body
    assert "preshared_key" not in body
    assert "provider_config" not in body
    assert "encrypted_provider_config" not in body

    assert "has_private_key" in body
    assert "has_preshared_key" in body
    assert "secret" not in response.text

    service.get.assert_called_once_with(42)


def test_get_profile_returns_null_when_missing() -> None:
    service = Mock()
    service.get.return_value = None

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_vpn_profile_service] = lambda: service

    try:
        response = client.get("/api/v1/vpn/profile")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() is None


def test_save_profile_returns_sanitized_metadata() -> None:
    service = Mock()
    service.get.return_value = make_read()

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_vpn_profile_service] = lambda: service

    payload = {
        "name": "Primary VPN",
        "enabled": True,
        "provider_config": "[Interface]\nPrivateKey = secret\n",
    }

    try:
        response = client.post(
            "/api/v1/vpn/profile",
            json=payload,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "id": 7,
        "name": "Primary VPN",
        "enabled": True,
        "has_private_key": True,
        "has_preshared_key": True,
    }

    service.save.assert_called_once_with(
        user_id=42,
        name="Primary VPN",
        provider_config="[Interface]\nPrivateKey = secret\n",
        enabled=True,
    )


def test_save_profile_maps_validation_error() -> None:
    service = Mock()
    service.save.side_effect = ValueError("invalid config")

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_vpn_profile_service] = lambda: service

    try:
        response = client.post(
            "/api/v1/vpn/profile",
            json={
                "name": "Primary VPN",
                "enabled": True,
                "provider_config": "broken",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid config"


def test_validate_profile_does_not_persist() -> None:
    service = Mock()
    service.validate.return_value = VpnProfileValidationResult(
        valid=True,
        interface_address="10.100.0.2/32",
        endpoint="109.172.55.99:51820",
        allowed_ips=("0.0.0.0/0",),
        has_private_key=True,
        has_preshared_key=True,
        reason=None,
    )

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_vpn_profile_service] = lambda: service

    try:
        response = client.post(
            "/api/v1/vpn/profile/validate",
            json={
                "provider_config": "[Interface]\nPrivateKey = secret\n",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "valid": True,
        "interface_address": "10.100.0.2/32",
        "endpoint": "109.172.55.99:51820",
        "allowed_ips": ["0.0.0.0/0"],
        "has_private_key": True,
        "has_preshared_key": True,
        "reason": None,
    }

    service.validate.assert_called_once()
    service.save.assert_not_called()


def test_apply_profile_returns_runtime_result() -> None:
    service = Mock()
    service.apply.return_value = AmneziaWGRuntimeManagerResult(
        applied=True,
        verified=True,
        rolled_back=False,
        rollback_verified=False,
        health_failed=False,
        reason=None,
    )

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_vpn_profile_service] = lambda: service

    try:
        response = client.post("/api/v1/vpn/profile/apply")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "applied": True,
        "verified": True,
        "no_change": False,
        "rolled_back": False,
        "rollback_verified": False,
        "health_failed": False,
        "reason": None,
    }

    service.apply.assert_called_once_with(42)


def test_apply_profile_maps_missing_profile() -> None:
    service = Mock()
    service.apply.side_effect = LookupError("vpn_profile_not_found")

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_vpn_profile_service] = lambda: service

    try:
        response = client.post("/api/v1/vpn/profile/apply")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "vpn_profile_not_found"


def test_apply_profile_maps_disabled_profile() -> None:
    service = Mock()
    service.apply.side_effect = ValueError("vpn_profile_disabled")

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_vpn_profile_service] = lambda: service

    try:
        response = client.post("/api/v1/vpn/profile/apply")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"] == "vpn_profile_disabled"


def test_import_current_runtime_returns_safe_profile_response() -> None:
    app.dependency_overrides[get_current_user] = make_user
    service = Mock()

    service.import_current_runtime.return_value = None
    service.get.return_value = VpnProfileRead(
        id=11,
        name="Current Brume VPN",
        enabled=True,
        has_private_key=True,
        has_preshared_key=True,
    )

    app.dependency_overrides[get_vpn_profile_service] = lambda: service

    try:
        response = client.post(
            "/api/v1/vpn/profile/import-current-runtime",
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    body = response.json()

    assert body == {
        "id": 11,
        "name": "Current Brume VPN",
        "enabled": True,
        "has_private_key": True,
        "has_preshared_key": True,
    }

    assert "private_key" not in body
    assert "preshared_key" not in body
    assert "provider_config" not in body
    assert "encrypted_provider_config" not in body

    assert body["has_private_key"] is True
    assert body["has_preshared_key"] is True

    service.import_current_runtime.assert_called_once_with(
        user_id=42,
    )
    service.get.assert_called_once_with(42)


def test_import_current_runtime_maps_value_error_to_422() -> None:
    app.dependency_overrides[get_current_user] = make_user
    service = Mock()

    service.import_current_runtime.side_effect = ValueError(
        "invalid VPN profile",
    )

    app.dependency_overrides[get_vpn_profile_service] = lambda: service

    try:
        response = client.post(
            "/api/v1/vpn/profile/import-current-runtime",
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid VPN profile"


def test_import_current_runtime_maps_runtime_error_to_502() -> None:
    app.dependency_overrides[get_current_user] = make_user
    service = Mock()

    service.import_current_runtime.side_effect = RuntimeError(
        "uci_get_failed",
    )

    app.dependency_overrides[get_vpn_profile_service] = lambda: service

    try:
        response = client.post(
            "/api/v1/vpn/profile/import-current-runtime",
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json()["detail"] == "uci_get_failed"


def test_start_vpn_uses_runtime_service_without_profile_apply() -> None:
    service = Mock()

    checked_at = datetime(
        2026,
        9,
        2,
        tzinfo=timezone.utc,
    )

    health = AmneziaWGRuntimeHealth(
        interface_exists=True,
        interface_up=True,
        expected_peer_found=True,
        expected_endpoint=True,
        listen_port=36360,
        latest_handshake=checked_at,
        rx_bytes=1234,
        tx_bytes=5678,
        endpoint_route_ok=True,
        healthy=True,
        reason=None,
        checked_at=checked_at,
    )

    service.start.return_value = health
    service.handshake_age_seconds.return_value = 3

    profile_service = Mock()

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_vpn_runtime_service] = lambda: service
    app.dependency_overrides[get_vpn_profile_service] = lambda: profile_service

    try:
        response = client.post("/api/v1/vpn/start")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    body = response.json()

    assert body["healthy"] is True
    assert body["interface_up"] is True
    assert body["listen_port"] == 36360
    assert body["rx_bytes"] == 1234
    assert body["tx_bytes"] == 5678
    assert body["handshake_age_seconds"] == 3
    assert body["in_sync"] is False

    service.start.assert_called_once_with("WireGuard")
    profile_service.apply.assert_not_called()
    profile_service.preflight_apply.assert_not_called()


def test_start_vpn_returns_bad_gateway_when_runtime_is_unhealthy() -> None:
    service = Mock()

    checked_at = datetime(
        2026,
        9,
        2,
        tzinfo=timezone.utc,
    )

    service.start.return_value = AmneziaWGRuntimeHealth(
        interface_exists=True,
        interface_up=False,
        expected_peer_found=True,
        expected_endpoint=True,
        listen_port=None,
        latest_handshake=None,
        rx_bytes=0,
        tx_bytes=0,
        endpoint_route_ok=True,
        healthy=False,
        reason="interface_down",
        checked_at=checked_at,
    )

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_vpn_runtime_service] = lambda: service

    try:
        response = client.post("/api/v1/vpn/start")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json()["detail"] == "interface_down"

    service.start.assert_called_once_with("WireGuard")


def test_stop_vpn_switches_to_wan_mode() -> None:
    service = Mock()

    checked_at = datetime(
        2026,
        9,
        2,
        tzinfo=timezone.utc,
    )

    health = AmneziaWGRuntimeHealth(
        interface_exists=True,
        interface_up=False,
        expected_peer_found=True,
        expected_endpoint=True,
        listen_port=None,
        latest_handshake=None,
        rx_bytes=1234,
        tx_bytes=5678,
        endpoint_route_ok=True,
        healthy=False,
        reason="interface_down",
        checked_at=checked_at,
    )

    service.stop.return_value = health
    service.handshake_age_seconds.return_value = None

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_vpn_runtime_service] = lambda: service

    try:
        response = client.post("/api/v1/vpn/stop")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    body = response.json()

    assert body["interface"] == "WireGuard"
    assert body["healthy"] is False
    assert body["interface_up"] is False
    assert body["traffic_mode"] == "wan"
    assert body["rx_bytes"] == 1234
    assert body["tx_bytes"] == 5678
    assert body["handshake_age_seconds"] is None
    assert body["in_sync"] is False

    service.stop.assert_called_once_with("WireGuard")
    service.handshake_age_seconds.assert_called_once_with(health)
