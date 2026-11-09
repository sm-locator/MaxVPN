from __future__ import annotations

from dataclasses import dataclass

from backend.services.smart_routing_import import (
    SmartRoutingImportItem,
    SmartRoutingImportStatus,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.smart_routing_rule import SmartRoutingRule


@dataclass(frozen=True, slots=True)
class SmartRoutingImportPlanItem:
    line: int
    resource: str
    target_type: str | None
    address_family: str | None
    status: SmartRoutingImportStatus
    error: str | None = None


@dataclass(frozen=True, slots=True)
class SmartRoutingImportPlan:
    items: tuple[SmartRoutingImportPlanItem, ...]
    new_items: tuple[SmartRoutingImportPlanItem, ...]


@dataclass(frozen=True, slots=True)
class SmartRoutingImportResult:
    requested: int
    added: int
    already_exists: int
    duplicates: int
    invalid: int
    rules: tuple[SmartRoutingRule, ...]


class ImportSmartRoutingUseCase:
    def __init__(self, db: Session) -> None:
        self._db = db

    def plan(
        self,
        user_id: int,
        items: list[SmartRoutingImportItem],
    ) -> SmartRoutingImportPlan:
        existing_rules = list(
            self._db.scalars(
                select(SmartRoutingRule).where(
                    SmartRoutingRule.user_id == user_id,
                    SmartRoutingRule.action == "direct",
                )
            ).all()
        )

        existing_keys = {
            (
                rule.target_type,
                rule.target.strip().lower().rstrip("."),
            )
            for rule in existing_rules
        }

        planned_keys: set[tuple[str, str]] = set()
        planned_items: list[SmartRoutingImportPlanItem] = []

        for item in items:
            if item.status is SmartRoutingImportStatus.INVALID:
                planned_items.append(
                    SmartRoutingImportPlanItem(
                        line=item.line,
                        resource=item.resource,
                        target_type=(
                            item.target_type.value
                            if item.target_type is not None
                            else None
                        ),
                        address_family=item.address_family,
                        status=SmartRoutingImportStatus.INVALID,
                        error=item.error,
                    )
                )
                continue

            if item.status is SmartRoutingImportStatus.DUPLICATE:
                planned_items.append(
                    SmartRoutingImportPlanItem(
                        line=item.line,
                        resource=item.resource,
                        target_type=(
                            item.target_type.value
                            if item.target_type is not None
                            else None
                        ),
                        address_family=item.address_family,
                        status=SmartRoutingImportStatus.DUPLICATE,
                    )
                )
                continue

            if item.target_type is None or item.address_family is None:
                planned_items.append(
                    SmartRoutingImportPlanItem(
                        line=item.line,
                        resource=item.resource,
                        target_type=None,
                        address_family=None,
                        status=SmartRoutingImportStatus.INVALID,
                        error="missing target type or address family",
                    )
                )
                continue

            key = (
                item.target_type.value,
                item.resource,
            )

            if key in existing_keys:
                planned_items.append(
                    SmartRoutingImportPlanItem(
                        line=item.line,
                        resource=item.resource,
                        target_type=item.target_type.value,
                        address_family=item.address_family,
                        status=SmartRoutingImportStatus.ALREADY_EXISTS,
                    )
                )
                continue

            if key in planned_keys:
                planned_items.append(
                    SmartRoutingImportPlanItem(
                        line=item.line,
                        resource=item.resource,
                        target_type=item.target_type.value,
                        address_family=item.address_family,
                        status=SmartRoutingImportStatus.DUPLICATE,
                    )
                )
                continue

            planned_keys.add(key)

            planned_items.append(
                SmartRoutingImportPlanItem(
                    line=item.line,
                    resource=item.resource,
                    target_type=item.target_type.value,
                    address_family=item.address_family,
                    status=SmartRoutingImportStatus.VALID,
                )
            )

        new_items = tuple(
            item
            for item in planned_items
            if item.status is SmartRoutingImportStatus.VALID
        )

        return SmartRoutingImportPlan(
            items=tuple(planned_items),
            new_items=new_items,
        )

    def execute(
        self,
        user_id: int,
        items: list[SmartRoutingImportItem],
    ) -> SmartRoutingImportResult:
        plan = self.plan(user_id=user_id, items=items)

        existing_rules = list(
            self._db.scalars(
                select(SmartRoutingRule).where(
                    SmartRoutingRule.user_id == user_id,
                    SmartRoutingRule.action == "direct",
                )
            ).all()
        )

        next_priority = (
            max(
                (rule.priority for rule in existing_rules),
                default=0,
            )
            + 1
        )

        added_rules: list[SmartRoutingRule] = []

        for item in plan.new_items:
            rule = SmartRoutingRule(
                user_id=user_id,
                target_type=item.target_type,
                target=item.resource,
                action="direct",
                priority=next_priority,
                address_family=item.address_family,
                enabled=True,
            )

            self._db.add(rule)
            added_rules.append(rule)
            next_priority += 1

        self._db.commit()

        for rule in added_rules:
            self._db.refresh(rule)

        return SmartRoutingImportResult(
            requested=len(plan.items),
            added=len(added_rules),
            already_exists=sum(
                item.status is SmartRoutingImportStatus.ALREADY_EXISTS
                for item in plan.items
            ),
            duplicates=sum(
                item.status is SmartRoutingImportStatus.DUPLICATE for item in plan.items
            ),
            invalid=sum(
                item.status is SmartRoutingImportStatus.INVALID for item in plan.items
            ),
            rules=tuple(added_rules),
        )
