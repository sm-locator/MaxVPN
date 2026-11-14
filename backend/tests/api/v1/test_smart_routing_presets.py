from unittest.mock import Mock

from backend.application.use_cases.add_russian_direct_preset import (
    RussianDirectPresetResult,
)
from backend.services.russian_direct_preset import RUSSIAN_DIRECT_PRESET
from fastapi.testclient import TestClient

from app.main import app


def test_russia_direct_preset_requires_authentication() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/smart-routing/presets/russia-direct",
    )

    assert response.status_code in {401, 403}


def test_russia_direct_preset_uses_current_user(
    monkeypatch,
) -> None:
    use_case = Mock()

    use_case.execute.return_value = RussianDirectPresetResult(
        requested=len(RUSSIAN_DIRECT_PRESET),
        added=len(RUSSIAN_DIRECT_PRESET),
        already_present=0,
        rules=(),
    )

    from app.api.v1.smart_routing_presets import (
        get_add_russian_direct_preset_use_case,
    )

    app.dependency_overrides[get_add_russian_direct_preset_use_case] = lambda: use_case

    from app.auth.dependencies import get_current_user
    from app.models.user import User

    user = User(
        id=42,
        email="test@example.com",
        password_hash="hashed",
        role="admin",
    )

    app.dependency_overrides[get_current_user] = lambda: user

    try:
        client = TestClient(app)

        response = client.post(
            "/api/v1/smart-routing/presets/russia-direct",
        )

        assert response.status_code == 200

        body = response.json()

        assert body["preset"] == "russia-direct"
        assert body["requested"] == len(RUSSIAN_DIRECT_PRESET)
        assert body["added"] == len(RUSSIAN_DIRECT_PRESET)
        assert body["already_present"] == 0
        assert body["total_domains"] == len(RUSSIAN_DIRECT_PRESET)

        use_case.execute.assert_called_once_with(42)
    finally:
        app.dependency_overrides.pop(
            get_add_russian_direct_preset_use_case,
            None,
        )
        app.dependency_overrides.pop(
            get_current_user,
            None,
        )
