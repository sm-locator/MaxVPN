import secrets
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.database.session import SessionLocal
from app.main import app
from app.models.roles import UserRole
from app.models.smart_routing_rule import SmartRoutingRule
from app.models.user import User
from app.services.user import UserService

client = TestClient(app)


def get_admin_user() -> tuple[User, bool]:
    db = SessionLocal()
    try:
        database_name = db.get_bind().url.database
        if database_name != "maxvpn_test":
            raise RuntimeError(
                "Refusing to seed Smart Routing CRUD test outside maxvpn_test; "
                f"current database is {database_name!r}"
            )

        admin = (
            db.query(User)
            .filter(User.role == UserRole.ADMIN)
            .order_by(User.id.asc())
            .first()
        )

        created_admin = False
        if admin is None:
            admin = UserService(db).create_admin(
                email=f"pytest-admin-{uuid4().hex}@example.invalid",
                password=secrets.token_urlsafe(32),
            )
            db.commit()
            db.refresh(admin)
            created_admin = True

        return (
            User(
                id=admin.id,
                email=admin.email,
                password_hash=admin.password_hash,
                role=admin.role,
            ),
            created_admin,
        )
    finally:
        db.close()


def test_real_postgres_smart_routing_crud() -> None:
    current_user, created_admin = get_admin_user()

    # Сохраняем прежнее состояние dependency override,
    # чтобы не затронуть другие тесты.
    had_previous_override = get_current_user in app.dependency_overrides
    previous_override = app.dependency_overrides.get(get_current_user)

    # Запоминаем ID созданного правила для гарантированной очистки.
    rule_id: int | None = None

    app.dependency_overrides[get_current_user] = lambda: current_user

    try:
        # CREATE
        create_response = client.post(
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

        assert create_response.status_code == 201

        created = create_response.json()
        rule_id = created["id"]

        assert created["target_type"] == "cidr"
        assert created["target"] == "1.1.1.0/24"
        assert created["action"] == "direct"
        assert created["priority"] == 100
        assert created["address_family"] == "ipv4"
        assert created["enabled"] is True

        # LIST
        list_response = client.get(
            "/api/v1/smart-routing/rules",
        )

        assert list_response.status_code == 200
        assert any(rule["id"] == rule_id for rule in list_response.json())

        # READ
        get_response = client.get(
            f"/api/v1/smart-routing/rules/{rule_id}",
        )

        assert get_response.status_code == 200
        assert get_response.json()["id"] == rule_id

        # UPDATE
        update_response = client.patch(
            f"/api/v1/smart-routing/rules/{rule_id}",
            json={
                "priority": 200,
                "enabled": False,
            },
        )

        assert update_response.status_code == 200

        updated = update_response.json()

        assert updated["priority"] == 200
        assert updated["enabled"] is False

        # DELETE
        delete_response = client.delete(
            f"/api/v1/smart-routing/rules/{rule_id}",
        )

        assert delete_response.status_code == 204

        # VERIFY DELETE
        missing_response = client.get(
            f"/api/v1/smart-routing/rules/{rule_id}",
        )

        assert missing_response.status_code == 404

    finally:
        # Восстанавливаем только изменённую зависимость.
        if had_previous_override:
            app.dependency_overrides[get_current_user] = previous_override
        else:
            app.dependency_overrides.pop(get_current_user, None)

        # Отдельная сессия нужна потому, что BaseRepository
        # фиксирует CRUD-операции собственными commit().
        cleanup_db = SessionLocal()

        try:
            # Удаляем правило, если тест завершился до штатного DELETE.
            if rule_id is not None:
                rule = (
                    cleanup_db.query(SmartRoutingRule)
                    .filter(
                        SmartRoutingRule.id == rule_id,
                        SmartRoutingRule.user_id == current_user.id,
                    )
                    .one_or_none()
                )

                if rule is not None:
                    cleanup_db.delete(rule)

            # Удаляем администратора только в том случае,
            # если он был создан специально для этого теста.
            if created_admin:
                admin = (
                    cleanup_db.query(User)
                    .filter(
                        User.id == current_user.id,
                        User.role == UserRole.ADMIN,
                    )
                    .one_or_none()
                )

                if admin is not None:
                    cleanup_db.delete(admin)

            cleanup_db.commit()

        except Exception:
            cleanup_db.rollback()
            raise

        finally:
            cleanup_db.close()
