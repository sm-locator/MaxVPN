from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.api.v1.smart_routing_dependency_groups import (
    get_group_repository,
    get_rule_repository,
)
from app.auth.dependencies import get_current_user
from app.database.dependencies import get_db
from app.main import app


def _user(user_id: int = 1):
    return SimpleNamespace(id=user_id)


def _rule(rule_id: int = 10, user_id: int = 1):
    return SimpleNamespace(
        id=rule_id,
        user_id=user_id,
        target_type="domain",
        target="maps.2gis.com",
        action="direct",
        priority=100,
        address_family="any",
        enabled=True,
    )


def _group(group_id: int = 1, user_id: int = 1):
    rule = _rule()
    item = SimpleNamespace(
        id=100,
        rule_id=rule.id,
        source="diagnostic",
        rule=rule,
    )
    return SimpleNamespace(
        id=group_id,
        user_id=user_id,
        site_domain="2gis.ru",
        title="2gis.ru",
        items=[item],
    )


def _client(group_repo, rule_repo, user_id=1):
    app.dependency_overrides[get_current_user] = lambda: _user(user_id)
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_group_repository] = lambda: group_repo
    app.dependency_overrides[get_rule_repository] = lambda: rule_repo
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_list_groups_is_scoped_to_current_user():
    group_repo = Mock()
    rule_repo = Mock()
    group_repo.get_by_user.return_value = [_group()]

    client = _client(group_repo, rule_repo, user_id=1)
    response = client.get("/api/v1/smart-routing/dependency-groups")

    assert response.status_code == 200
    assert response.json()[0]["site_domain"] == "2gis.ru"
    group_repo.get_by_user.assert_called_once_with(1)


def test_create_group_normalizes_domain():
    group_repo = Mock()
    rule_repo = Mock()
    group = _group()
    group_repo.get_or_create.return_value = group

    client = _client(group_repo, rule_repo)
    response = client.post(
        "/api/v1/smart-routing/dependency-groups",
        json={"site_domain": "HTTPS://2GIS.RU/", "title": "2GIS"},
    )

    assert response.status_code == 201
    group_repo.get_or_create.assert_called_once_with(
        1,
        "https://2gis.ru",
        title="2GIS",
    )


def test_add_rule_requires_ownership():
    group_repo = Mock()
    rule_repo = Mock()
    group_repo.get_by_user.return_value = [_group()]
    rule_repo.get_by_id.return_value = None

    client = _client(group_repo, rule_repo)
    response = client.post(
        "/api/v1/smart-routing/dependency-groups/1/rules",
        json={"rule_id": 999},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Smart Routing rule not found"


def test_add_rule_to_owned_group():
    group_repo = Mock()
    rule_repo = Mock()
    group = _group()
    group_repo.get_by_user.return_value = [group]
    rule = _rule()
    rule_repo.get_by_id.return_value = rule

    client = _client(group_repo, rule_repo)
    response = client.post(
        "/api/v1/smart-routing/dependency-groups/1/rules",
        json={"rule_id": 10, "source": "diagnostic"},
    )

    assert response.status_code == 200
    group_repo.add_rule.assert_called_once_with(
        group,
        10,
        source="diagnostic",
    )


def test_foreign_group_is_not_accessible():
    group_repo = Mock()
    rule_repo = Mock()
    group_repo.get_by_user.return_value = []

    client = _client(group_repo, rule_repo)
    response = client.post(
        "/api/v1/smart-routing/dependency-groups/1/rules",
        json={"rule_id": 10},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Dependency group not found"


def test_remove_rule_from_owned_group():
    group_repo = Mock()
    rule_repo = Mock()
    group = _group()
    group_repo.get_by_user.return_value = [group]

    client = _client(group_repo, rule_repo)
    response = client.delete(
        "/api/v1/smart-routing/dependency-groups/1/rules/10",
    )

    assert response.status_code == 200
    group_repo.remove_rule.assert_called_once_with(group, 10)


def test_remove_rule_from_foreign_group_is_not_allowed():
    group_repo = Mock()
    rule_repo = Mock()
    group_repo.get_by_user.return_value = []

    client = _client(group_repo, rule_repo)
    response = client.delete(
        "/api/v1/smart-routing/dependency-groups/1/rules/10",
    )

    assert response.status_code == 404
    group_repo.remove_rule.assert_not_called()
