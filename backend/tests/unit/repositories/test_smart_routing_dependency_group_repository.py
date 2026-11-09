from unittest.mock import Mock

from backend.app.repositories.smart_routing_dependency_group import (
    SmartRoutingDependencyGroupRepository,
)

from app.models.smart_routing_dependency_group import (
    SmartRoutingDependencyGroup,
    SmartRoutingDependencyGroupItem,
)


def test_get_or_create_returns_existing_group():
    db = Mock()
    repository = SmartRoutingDependencyGroupRepository(db)

    existing = SmartRoutingDependencyGroup(
        user_id=42,
        site_domain="2gis.ru",
        title="2gis.ru",
    )

    repository.get_by_user_and_domain = Mock(
        return_value=existing,
    )

    result = repository.get_or_create(
        42,
        "2gis.ru",
    )

    assert result is existing
    db.add.assert_not_called()


def test_get_or_create_creates_group():
    db = Mock()

    repository = SmartRoutingDependencyGroupRepository(db)
    repository.get_by_user_and_domain = Mock(
        return_value=None,
    )

    result = repository.get_or_create(
        42,
        "2gis.ru",
    )

    assert result.user_id == 42
    assert result.site_domain == "2gis.ru"
    assert result.title == "2gis.ru"

    db.add.assert_called_once_with(result)
    db.flush.assert_called_once()
    db.refresh.assert_called_once_with(result)


def test_add_rule_is_idempotent():
    db = Mock()
    repository = SmartRoutingDependencyGroupRepository(db)

    group = SmartRoutingDependencyGroup(
        user_id=42,
        site_domain="2gis.ru",
        title="2gis.ru",
    )

    first = repository.add_rule(
        group,
        10,
        source="diagnostic",
    )

    second = repository.add_rule(
        group,
        10,
        source="diagnostic",
    )

    assert first is second
    assert len(group.items) == 1
    assert group.items[0].rule_id == 10

    assert db.add.call_count == 1


def test_remove_rule_returns_false_when_missing():
    db = Mock()
    repository = SmartRoutingDependencyGroupRepository(db)

    group = SmartRoutingDependencyGroup(
        user_id=42,
        site_domain="2gis.ru",
        title="2gis.ru",
    )

    assert repository.remove_rule(group, 999) is False
    db.delete.assert_not_called()


def test_remove_rule_deletes_existing_item():
    db = Mock()
    repository = SmartRoutingDependencyGroupRepository(db)

    group = SmartRoutingDependencyGroup(
        user_id=42,
        site_domain="2gis.ru",
        title="2gis.ru",
    )

    item = SmartRoutingDependencyGroupItem(
        group_id=1,
        rule_id=10,
        source="diagnostic",
    )

    group.items.append(item)

    assert repository.remove_rule(group, 10) is True
    db.delete.assert_called_once_with(item)
    assert group.items == []
