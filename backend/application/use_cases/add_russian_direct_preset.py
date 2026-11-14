from __future__ import annotations

from dataclasses import dataclass

from backend.services.russian_direct_preset import RUSSIAN_DIRECT_PRESET
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.smart_routing_rule import SmartRoutingRule


@dataclass(frozen=True, slots=True)
class RussianDirectPresetResult:
    requested: int
    added: int
    already_present: int
    rules: tuple[SmartRoutingRule, ...]


class AddRussianDirectPresetUseCase:
    def __init__(self, db: Session) -> None:
        self._db = db

    def execute(self, user_id: int) -> RussianDirectPresetResult:
        existing = list(
            self._db.scalars(
                select(SmartRoutingRule).where(
                    SmartRoutingRule.user_id == user_id,
                    SmartRoutingRule.target_type == "domain",
                )
            ).all()
        )

        existing_domains = {
            rule.target.strip().lower().rstrip(".") for rule in existing
        }

        next_priority = (
            max(
                (rule.priority for rule in existing),
                default=0,
            )
            + 1
        )

        added_rules: list[SmartRoutingRule] = []
        already_present = 0

        for entry in RUSSIAN_DIRECT_PRESET:
            domain = entry.domain.lower().rstrip(".")

            if domain in existing_domains:
                already_present += 1
                continue

            rule = SmartRoutingRule(
                user_id=user_id,
                target_type="domain",
                target=domain,
                action="direct",
                priority=next_priority,
                address_family="any",
                enabled=True,
            )
            self._db.add(rule)
            added_rules.append(rule)
            existing_domains.add(domain)
            next_priority += 1

        self._db.commit()

        for rule in added_rules:
            self._db.refresh(rule)

        return RussianDirectPresetResult(
            requested=len(RUSSIAN_DIRECT_PRESET),
            added=len(added_rules),
            already_present=already_present,
            rules=tuple(added_rules),
        )
