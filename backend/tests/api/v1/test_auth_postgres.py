import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.database.dependencies import get_db
from app.main import app
from app.models.user import User


@pytest.fixture
def auth_database():
    url = make_url(os.environ["TEST_DATABASE_URL"])
    if url.database != "maxvpn_test":
        raise RuntimeError("Auth integration checks require maxvpn_test")
    schema = "auth_review_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    User.__table__.create(engine)
    factory = sessionmaker(bind=engine)

    def sessions():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = sessions
    try:
        yield factory
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def test_concurrent_bootstrap_creates_exactly_one_admin(auth_database):
    def bootstrap(index):
        return TestClient(app).post(
            "/api/v1/auth/bootstrap",
            json={
                "email": f"admin{index}@example.com",
                "password": "disposable-password",
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(bootstrap, [1, 2]))
    assert sorted(response.status_code for response in responses) == [200, 403]
    with auth_database() as db:
        assert len(db.scalars(select(User).where(User.role == "admin")).all()) == 1


def test_password_change_revokes_existing_token_without_changing_email(auth_database):
    client = TestClient(app)
    data = {"email": "admin@example.com", "password": "disposable-password"}
    created = client.post("/api/v1/auth/bootstrap", json=data)
    assert created.status_code == 200
    old = {"Authorization": "Bearer " + created.json()["access_token"]}
    assert client.get("/api/v1/auth/me", headers=old).status_code == 200
    changed = client.put(
        "/api/v1/auth/me/credentials",
        headers=old,
        json={**data, "password": "new-disposable-password"},
    )
    assert changed.status_code == 200
    assert client.get("/api/v1/auth/me", headers=old).status_code == 401
    new = {"Authorization": "Bearer " + changed.json()["access_token"]}
    assert client.get("/api/v1/auth/me", headers=new).status_code == 200
    assert (
        client.post(
            "/api/v1/auth/login",
            data={"username": data["email"], "password": data["password"]},
        ).status_code
        == 401
    )


def test_weak_password_and_duplicate_registration_have_controlled_errors(auth_database):
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/auth/bootstrap",
            json={"email": "admin@example.com", "password": ""},
        ).status_code
        == 422
    )
    data = {"email": "user@example.com", "password": "disposable-password"}
    assert client.post("/api/v1/auth/register", json=data).status_code == 200
    assert client.post("/api/v1/auth/register", json=data).status_code == 409
