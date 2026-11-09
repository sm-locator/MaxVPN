from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.database.dependencies import get_db
from app.main import app
from app.models.smart_routing_rule import SmartRoutingRule
from app.models.user import User

client = TestClient(app)


def make_user(user_id: int = 42) -> User:
    return User(
        id=user_id,
        email=f"user{user_id}@example.com",
        password_hash="hash",
        role="user",
    )


def make_rule(
    *,
    target_type: str,
    target: str,
    action: str = "direct",
) -> SmartRoutingRule:
    return SmartRoutingRule(
        id=1,
        user_id=42,
        target_type=target_type,
        target=target,
        action=action,
        priority=100,
        address_family="any" if target_type == "domain" else "ipv4",
        enabled=True,
    )


def test_preview_import_detects_existing_rules() -> None:
    db = Mock()
    db.scalars.return_value.all.return_value = [
        make_rule(
            target_type="domain",
            target="example.com",
        ),
        make_rule(
            target_type="cidr",
            target="192.168.1.0/24",
        ),
    ]

    app.dependency_overrides[get_current_user] = lambda: make_user()
    app.dependency_overrides[get_db] = lambda: db

    try:
        response = client.post(
            "/api/v1/smart-routing/import/preview",
            files={
                "file": (
                    "test.txt",
                    (b"example.com\nnew.example.com\n192.168.1.0/24\n192.168.2.0/24\n"),
                    "text/plain",
                )
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["total"] == 4
        assert body["new"] == 2
        assert body["duplicates"] == 0
        assert body["already_exists"] == 2
        assert body["invalid"] == 0

        assert body["items"] == [
            {
                "line": 1,
                "resource": "example.com",
                "target_type": "domain",
                "address_family": "any",
                "status": "already_exists",
                "error": None,
            },
            {
                "line": 2,
                "resource": "new.example.com",
                "target_type": "domain",
                "address_family": "any",
                "status": "valid",
                "error": None,
            },
            {
                "line": 3,
                "resource": "192.168.1.0/24",
                "target_type": "cidr",
                "address_family": "ipv4",
                "status": "already_exists",
                "error": None,
            },
            {
                "line": 4,
                "resource": "192.168.2.0/24",
                "target_type": "cidr",
                "address_family": "ipv4",
                "status": "valid",
                "error": None,
            },
        ]
    finally:
        app.dependency_overrides.clear()


def test_preview_import_does_not_write_to_database() -> None:
    db = Mock()
    db.scalars.return_value.all.return_value = []

    app.dependency_overrides[get_current_user] = lambda: make_user()
    app.dependency_overrides[get_db] = lambda: db

    try:
        response = client.post(
            "/api/v1/smart-routing/import/preview",
            files={
                "file": (
                    "test.txt",
                    b"example.com\n192.168.1.10\n",
                    "text/plain",
                )
            },
        )

        assert response.status_code == 200
        db.add.assert_not_called()
        db.commit.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_preview_import_requires_authentication() -> None:
    app.dependency_overrides[get_db] = lambda: Mock()

    try:
        response = client.post(
            "/api/v1/smart-routing/import/preview",
            files={
                "file": (
                    "test.txt",
                    b"example.com\n",
                    "text/plain",
                )
            },
        )

        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_import_creates_only_new_rules() -> None:
    repository_rules = [
        SmartRoutingRule(
            id=1,
            user_id=42,
            target_type="domain",
            target="existing.example.com",
            action="direct",
            priority=100,
            address_family="any",
            enabled=True,
        )
    ]

    class MockScalars:
        def all(self):
            return repository_rules

    db = Mock()
    db.scalars.return_value = MockScalars()

    app.dependency_overrides[get_current_user] = lambda: make_user()
    app.dependency_overrides[get_db] = lambda: db

    try:
        response = client.post(
            "/api/v1/smart-routing/import",
            files={
                "file": (
                    "test.txt",
                    (b"existing.example.com\nnew.example.com\n192.168.10.0/24\n"),
                    "text/plain",
                )
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["requested"] == 3
        assert body["added"] == 2
        assert body["already_exists"] == 1
        assert body["duplicates"] == 0
        assert body["invalid"] == 0

        assert len(body["rules"]) == 2

        first = body["rules"][0]
        second = body["rules"][1]

        assert first["target"] == "new.example.com"
        assert first["target_type"] == "domain"
        assert first["action"] == "direct"
        assert first["priority"] == 101
        assert first["address_family"] == "any"

        assert second["target"] == "192.168.10.0/24"
        assert second["target_type"] == "cidr"
        assert second["action"] == "direct"
        assert second["priority"] == 102
        assert second["address_family"] == "ipv4"

        db.commit.assert_called_once()
    finally:
        app.dependency_overrides.clear()


def test_import_is_idempotent_for_repeated_file() -> None:
    existing_rules = [
        SmartRoutingRule(
            id=1,
            user_id=42,
            target_type="domain",
            target="example.com",
            action="direct",
            priority=100,
            address_family="any",
            enabled=True,
        )
    ]

    class MockScalars:
        def all(self):
            return existing_rules

    db = Mock()
    db.scalars.return_value = MockScalars()

    app.dependency_overrides[get_current_user] = lambda: make_user()
    app.dependency_overrides[get_db] = lambda: db

    try:
        response = client.post(
            "/api/v1/smart-routing/import",
            files={
                "file": (
                    "test.txt",
                    b"example.com\n",
                    "text/plain",
                )
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["requested"] == 1
        assert body["added"] == 0
        assert body["already_exists"] == 1
        assert body["duplicates"] == 0
        assert body["invalid"] == 0
        assert body["rules"] == []

        db.add.assert_not_called()
        db.commit.assert_called_once()
    finally:
        app.dependency_overrides.clear()
