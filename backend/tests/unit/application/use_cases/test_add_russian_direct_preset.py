from unittest.mock import Mock

from backend.application.use_cases.add_russian_direct_preset import (
    AddRussianDirectPresetUseCase,
)
from backend.services.russian_direct_preset import (
    RUSSIAN_DIRECT_PRESET,
)

from app.models.smart_routing_rule import SmartRoutingRule


def test_russian_direct_preset_contains_unique_domains() -> None:
    domains = [entry.domain for entry in RUSSIAN_DIRECT_PRESET]

    assert len(domains) == len(set(domains))


def test_add_russian_direct_preset_creates_only_missing_domains() -> None:
    db = Mock()

    existing = SmartRoutingRule(
        id=100,
        user_id=1,
        target_type="domain",
        target="vk.com",
        action="direct",
        priority=100,
        address_family="any",
        enabled=True,
    )
    db.scalars.return_value.all.return_value = [existing]

    result = AddRussianDirectPresetUseCase(db).execute(user_id=1)

    assert result.requested == len(RUSSIAN_DIRECT_PRESET)
    assert result.added == len(RUSSIAN_DIRECT_PRESET) - 1
    assert result.already_present == 1

    added_domains = [call.args[0].target for call in db.add.call_args_list]

    assert "vk.com" not in added_domains
    assert all(
        domain in {entry.domain for entry in RUSSIAN_DIRECT_PRESET}
        for domain in added_domains
    )

    db.commit.assert_called_once()


def test_add_russian_direct_preset_is_idempotent() -> None:
    db = Mock()

    existing = [
        SmartRoutingRule(
            id=index,
            user_id=1,
            target_type="domain",
            target=entry.domain,
            action="direct",
            priority=100 + index,
            address_family="any",
            enabled=True,
        )
        for index, entry in enumerate(
            RUSSIAN_DIRECT_PRESET,
            start=1,
        )
    ]

    db.scalars.return_value.all.return_value = existing

    result = AddRussianDirectPresetUseCase(db).execute(user_id=1)

    assert result.requested == len(RUSSIAN_DIRECT_PRESET)
    assert result.added == 0
    assert result.already_present == len(RUSSIAN_DIRECT_PRESET)
    assert db.add.call_count == 0
    db.commit.assert_called_once()
