from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.api.v1.smart_routing import get_repository
from app.auth.dependencies import get_current_user
from app.main import app
from app.models.smart_routing_rule import SmartRoutingRule
from app.models.user import User

client = TestClient(app)


def make_user(user_id: int) -> User:
    return User(
        id=user_id,
        email=f"user{user_id}@example.com",
        password_hash="hash",
        role="user",
    )


def mock_create(
    rule: SmartRoutingRule,
) -> SmartRoutingRule:
    rule.id = 10
    return rule


def make_rule(
    *,
    rule_id: int,
    user_id: int,
) -> SmartRoutingRule:
    return SmartRoutingRule(
        id=rule_id,
        user_id=user_id,
        target_type="cidr",
        target="1.1.1.0/24",
        action="direct",
        priority=100,
        address_family="ipv4",
        enabled=True,
    )


def test_create_rule_uses_current_user_id() -> None:
    repository = Mock()
    repository.create.side_effect = mock_create

    app.dependency_overrides[get_current_user] = lambda: make_user(42)
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        response = client.post(
            "/api/v1/smart-routing/rules",
            json={
                "target_type": "cidr",
                "target": "1.1.1.0/24",
                "action": "direct",
                "priority": 100,
                "address_family": "ipv4",
                "enabled": True,
            },
        )

        assert response.status_code == 201

        created = repository.create.call_args.args[0]

        assert created.user_id == 42
        assert created.target_type == "cidr"
        assert created.target == "1.1.1.0/24"
        assert created.action == "direct"
        assert created.priority == 100
        assert created.address_family == "ipv4"
        assert created.enabled is True
    finally:
        app.dependency_overrides.clear()


def test_create_rule_does_not_accept_user_id_from_payload() -> None:
    repository = Mock()
    repository.create.side_effect = mock_create

    app.dependency_overrides[get_current_user] = lambda: make_user(42)
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        response = client.post(
            "/api/v1/smart-routing/rules",
            json={
                "user_id": 999,
                "target_type": "cidr",
                "target": "1.1.1.0/24",
                "action": "direct",
                "priority": 100,
            },
        )

        assert response.status_code == 201

        created = repository.create.call_args.args[0]

        assert created.user_id == 42
    finally:
        app.dependency_overrides.clear()


def test_list_rules_is_scoped_to_current_user() -> None:
    repository = Mock()
    repository.get_by_user.return_value = [
        make_rule(rule_id=10, user_id=42),
    ]

    app.dependency_overrides[get_current_user] = lambda: make_user(42)
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        response = client.get("/api/v1/smart-routing/rules")

        assert response.status_code == 200
        assert response.json() == [
            {
                "id": 10,
                "target_type": "cidr",
                "target": "1.1.1.0/24",
                "action": "direct",
                "priority": 100,
                "address_family": "ipv4",
                "enabled": True,
            }
        ]

        repository.get_by_user.assert_called_once_with(42)
    finally:
        app.dependency_overrides.clear()


def test_get_rule_uses_current_user_scope() -> None:
    repository = Mock()
    repository.get_by_id.return_value = make_rule(
        rule_id=10,
        user_id=42,
    )

    app.dependency_overrides[get_current_user] = lambda: make_user(42)
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        response = client.get("/api/v1/smart-routing/rules/10")

        assert response.status_code == 200
        repository.get_by_id.assert_called_once_with(42, 10)
    finally:
        app.dependency_overrides.clear()


def test_get_foreign_rule_returns_404() -> None:
    repository = Mock()
    repository.get_by_id.return_value = None

    app.dependency_overrides[get_current_user] = lambda: make_user(42)
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        response = client.get("/api/v1/smart-routing/rules/10")

        assert response.status_code == 404
        assert response.json() == {
            "detail": "Smart Routing rule not found",
        }

        repository.get_by_id.assert_called_once_with(42, 10)
    finally:
        app.dependency_overrides.clear()


def test_update_rule_is_scoped_to_current_user() -> None:
    repository = Mock()
    rule = make_rule(rule_id=10, user_id=42)
    repository.get_by_id.return_value = rule
    repository.update.side_effect = lambda value: value

    app.dependency_overrides[get_current_user] = lambda: make_user(42)
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        response = client.patch(
            "/api/v1/smart-routing/rules/10",
            json={
                "priority": 200,
                "enabled": False,
            },
        )

        assert response.status_code == 200
        assert rule.priority == 200
        assert rule.enabled is False

        repository.get_by_id.assert_called_once_with(42, 10)
        repository.update.assert_called_once_with(rule)
    finally:
        app.dependency_overrides.clear()


def test_update_foreign_rule_returns_404() -> None:
    repository = Mock()
    repository.get_by_id.return_value = None

    app.dependency_overrides[get_current_user] = lambda: make_user(42)
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        response = client.patch(
            "/api/v1/smart-routing/rules/10",
            json={"priority": 200},
        )

        assert response.status_code == 404
        repository.update.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_delete_rule_is_scoped_to_current_user() -> None:
    repository = Mock()
    rule = make_rule(rule_id=10, user_id=42)
    repository.get_by_id.return_value = rule

    app.dependency_overrides[get_current_user] = lambda: make_user(42)
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        response = client.delete("/api/v1/smart-routing/rules/10")

        assert response.status_code == 204
        assert response.content == b""

        repository.get_by_id.assert_called_once_with(42, 10)
        repository.delete.assert_called_once_with(rule)
    finally:
        app.dependency_overrides.clear()


def test_delete_foreign_rule_returns_404() -> None:
    repository = Mock()
    repository.get_by_id.return_value = None

    app.dependency_overrides[get_current_user] = lambda: make_user(42)
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        response = client.delete("/api/v1/smart-routing/rules/10")

        assert response.status_code == 404
        repository.delete.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_create_rejects_negative_priority() -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user(42)
    app.dependency_overrides[get_repository] = lambda: Mock()

    try:
        response = client.post(
            "/api/v1/smart-routing/rules",
            json={
                "target_type": "cidr",
                "target": "1.1.1.0/24",
                "action": "direct",
                "priority": -1,
            },
        )

        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_create_rejects_invalid_action() -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user(42)
    app.dependency_overrides[get_repository] = lambda: Mock()

    try:
        response = client.post(
            "/api/v1/smart-routing/rules",
            json={
                "target_type": "cidr",
                "target": "1.1.1.0/24",
                "action": "invalid",
                "priority": 100,
            },
        )

        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
