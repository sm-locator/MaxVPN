from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.smart_routing_rule import SmartRoutingRule
from app.repositories.base import BaseRepository


class SmartRoutingRuleRepository(BaseRepository[SmartRoutingRule]):
    def __init__(self, db: Session):
        super().__init__(SmartRoutingRule, db)

    def get_by_user(self, user_id: int) -> list[SmartRoutingRule]:
        stmt = (
            select(SmartRoutingRule)
            .where(SmartRoutingRule.user_id == user_id)
            .order_by(SmartRoutingRule.priority, SmartRoutingRule.id)
        )
        return list(self.db.scalars(stmt).all())

    def get_by_id(
        self,
        user_id: int,
        rule_id: int,
    ) -> SmartRoutingRule | None:
        stmt = select(SmartRoutingRule).where(
            SmartRoutingRule.id == rule_id,
            SmartRoutingRule.user_id == user_id,
        )
        return self.db.scalar(stmt)
