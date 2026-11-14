from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.smart_routing_dependency_group import (
    SmartRoutingDependencyGroup,
    SmartRoutingDependencyGroupItem,
)


class SmartRoutingDependencyGroupRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_user_and_domain(
        self,
        user_id: int,
        site_domain: str,
    ) -> SmartRoutingDependencyGroup | None:
        stmt = (
            select(SmartRoutingDependencyGroup)
            .where(
                SmartRoutingDependencyGroup.user_id == user_id,
                SmartRoutingDependencyGroup.site_domain == site_domain,
            )
            .options(
                selectinload(SmartRoutingDependencyGroup.items).selectinload(
                    SmartRoutingDependencyGroupItem.rule
                )
            )
        )

        return self.db.scalar(stmt)

    def get_by_user(
        self,
        user_id: int,
    ) -> list[SmartRoutingDependencyGroup]:
        stmt = (
            select(SmartRoutingDependencyGroup)
            .where(
                SmartRoutingDependencyGroup.user_id == user_id,
            )
            .order_by(
                SmartRoutingDependencyGroup.site_domain,
                SmartRoutingDependencyGroup.id,
            )
            .options(
                selectinload(SmartRoutingDependencyGroup.items).selectinload(
                    SmartRoutingDependencyGroupItem.rule
                )
            )
        )

        return list(self.db.scalars(stmt).unique().all())

    def get_or_create(
        self,
        user_id: int,
        site_domain: str,
        *,
        title: str | None = None,
    ) -> SmartRoutingDependencyGroup:
        group = self.get_by_user_and_domain(
            user_id,
            site_domain,
        )

        if group is not None:
            return group

        group = SmartRoutingDependencyGroup(
            user_id=user_id,
            site_domain=site_domain,
            title=title or site_domain,
        )

        self.db.add(group)
        self.db.flush()
        self.db.refresh(group)

        return group

    def add_rule(
        self,
        group: SmartRoutingDependencyGroup,
        rule_id: int,
        *,
        source: str = "diagnostic",
    ) -> SmartRoutingDependencyGroupItem:
        existing = next(
            (item for item in group.items if item.rule_id == rule_id),
            None,
        )

        if existing is not None:
            return existing

        item = SmartRoutingDependencyGroupItem(
            group_id=group.id,
            rule_id=rule_id,
            source=source,
        )

        self.db.add(item)
        self.db.flush()

        group.items.append(item)

        return item

    def remove_rule(
        self,
        group: SmartRoutingDependencyGroup,
        rule_id: int,
    ) -> bool:
        item = next(
            (item for item in group.items if item.rule_id == rule_id),
            None,
        )

        if item is None:
            return False

        self.db.delete(item)
        self.db.flush()

        group.items.remove(item)
        return True
