from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.main import app
from app.models.user import User

client = TestClient(app)


def make_user() -> User:
    return User(
        id=42,
        email="user@example.com",
        password_hash="hash",
        role="user",
    )


class FakeHealth:
    status = Mock(value="healthy")
    reason = None


def test_status_requires_authentication() -> None:
    response = client.get("/api/v1/status")

    assert response.status_code == 401


def test_status_returns_system_components(
    monkeypatch,
) -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user()

    health_use_case = Mock()
    health_use_case.execute.return_value = FakeHealth()

    monkeypatch.setattr(
        "app.api.v1.status.get_wireguard_health_use_case",
        lambda: health_use_case,
    )

    class FakeSmartRouting:
        def verify(self):
            result = Mock()
            result.healthy = True
            result.reason = None
            return result

    monkeypatch.setattr(
        "app.api.v1.status.get_smart_routing_service",
        lambda: FakeSmartRouting(),
    )

    class FakeExecutor:
        def run(self, command):
            result = Mock()
            result.returncode = 0
            result.stdout = "2: br-lan: <BROADCAST,UP,LOWER_UP>"
            result.stderr = ""
            return result

    monkeypatch.setattr(
        "app.api.v1.status.SSHRemoteCommandExecutor",
        lambda **kwargs: FakeExecutor(),
    )

    try:
        response = client.get("/api/v1/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "router": {
            "status": "connected",
            "reason": None,
        },
        "vpn": {
            "status": "healthy",
            "reason": None,
        },
        "smart_routing": {
            "status": "healthy",
            "reason": None,
        },
    }
