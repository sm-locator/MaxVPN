from unittest.mock import Mock

from backend.application.use_cases.import_smart_routing import (
    ImportSmartRoutingUseCase,
)
from backend.services.smart_routing_import import (
    SmartRoutingImportItem,
    SmartRoutingImportStatus,
    SmartRoutingImportType,
)


def make_item(
    *,
    line: int,
    resource: str,
    target_type: SmartRoutingImportType,
    address_family: str,
    status: SmartRoutingImportStatus = SmartRoutingImportStatus.VALID,
) -> SmartRoutingImportItem:
    return SmartRoutingImportItem(
        line=line,
        resource=resource,
        target_type=target_type,
        address_family=address_family,
        status=status,
    )


def make_rule(
    *,
    rule_id: int,
    target_type: str,
    target: str,
    priority: int,
    action: str = "direct",
    address_family: str = "any",
) -> Mock:
    rule = Mock()
    rule.id = rule_id
    rule.user_id = 42
    rule.target_type = target_type
    rule.target = target
    rule.priority = priority
    rule.action = action
    rule.address_family = address_family
    rule.enabled = True
    return rule


def make_db(existing_rules: list[Mock]) -> Mock:
    db = Mock()
    db.scalars.return_value.all.return_value = existing_rules
    return db


def test_import_creates_new_rules_with_incrementing_priorities() -> None:
    db = make_db(
        [
            make_rule(
                rule_id=1,
                target_type="domain",
                target="existing.example.com",
                priority=100,
            ),
        ]
    )

    items = [
        make_item(
            line=1,
            resource="one.example.com",
            target_type=SmartRoutingImportType.DOMAIN,
            address_family="any",
        ),
        make_item(
            line=2,
            resource="192.168.1.0/24",
            target_type=SmartRoutingImportType.CIDR,
            address_family="ipv4",
        ),
    ]

    result = ImportSmartRoutingUseCase(db).execute(
        user_id=42,
        items=items,
    )

    assert result.requested == 2
    assert result.added == 2
    assert result.already_exists == 0
    assert result.duplicates == 0
    assert result.invalid == 0

    assert len(result.rules) == 2

    first = result.rules[0]
    second = result.rules[1]

    assert first.user_id == 42
    assert first.target_type == "domain"
    assert first.target == "one.example.com"
    assert first.action == "direct"
    assert first.priority == 101
    assert first.address_family == "any"
    assert first.enabled is True

    assert second.user_id == 42
    assert second.target_type == "cidr"
    assert second.target == "192.168.1.0/24"
    assert second.action == "direct"
    assert second.priority == 102
    assert second.address_family == "ipv4"
    assert second.enabled is True

    db.commit.assert_called_once()


def test_import_skips_existing_rules() -> None:
    db = make_db(
        [
            make_rule(
                rule_id=1,
                target_type="domain",
                target="example.com",
                priority=100,
            ),
        ]
    )

    items = [
        make_item(
            line=1,
            resource="example.com",
            target_type=SmartRoutingImportType.DOMAIN,
            address_family="any",
        ),
        make_item(
            line=2,
            resource="new.example.com",
            target_type=SmartRoutingImportType.DOMAIN,
            address_family="any",
        ),
    ]

    result = ImportSmartRoutingUseCase(db).execute(
        user_id=42,
        items=items,
    )

    assert result.requested == 2
    assert result.added == 1
    assert result.already_exists == 1
    assert result.duplicates == 0
    assert result.invalid == 0

    assert result.rules[0].target == "new.example.com"
    assert result.rules[0].priority == 101


def test_import_skips_duplicates_from_parser() -> None:
    db = make_db([])

    items = [
        make_item(
            line=1,
            resource="example.com",
            target_type=SmartRoutingImportType.DOMAIN,
            address_family="any",
            status=SmartRoutingImportStatus.VALID,
        ),
        make_item(
            line=2,
            resource="example.com",
            target_type=SmartRoutingImportType.DOMAIN,
            address_family="any",
            status=SmartRoutingImportStatus.DUPLICATE,
        ),
    ]

    result = ImportSmartRoutingUseCase(db).execute(
        user_id=42,
        items=items,
    )

    assert result.requested == 2
    assert result.added == 1
    assert result.already_exists == 0
    assert result.duplicates == 1
    assert result.invalid == 0


def test_import_skips_invalid_items() -> None:
    db = make_db([])

    items = [
        SmartRoutingImportItem(
            line=1,
            resource="https://example.com/",
            target_type=None,
            address_family=None,
            status=SmartRoutingImportStatus.INVALID,
            error="invalid domain",
        ),
    ]

    result = ImportSmartRoutingUseCase(db).execute(
        user_id=42,
        items=items,
    )

    assert result.requested == 1
    assert result.added == 0
    assert result.already_exists == 0
    assert result.duplicates == 0
    assert result.invalid == 1
    assert result.rules == ()
    db.commit.assert_called_once()


def test_import_uses_only_direct_rules_for_existing_check() -> None:
    db = make_db([])

    items = [
        make_item(
            line=1,
            resource="vpn.example.com",
            target_type=SmartRoutingImportType.DOMAIN,
            address_family="any",
        ),
    ]

    result = ImportSmartRoutingUseCase(db).execute(
        user_id=42,
        items=items,
    )

    assert result.added == 1
    assert result.already_exists == 0
    assert result.rules[0].target == "vpn.example.com"
    assert result.rules[0].priority == 1
