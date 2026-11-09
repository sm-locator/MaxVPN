from __future__ import annotations

from backend.models.smart_routing_rule_data import SmartRoutingRuleData
from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.services.smart_routing_policy_builder import (
    SmartRoutingPolicyBuilder,
)
from sqlalchemy.orm import Session


class SmartRoutingPolicyService:
    def __init__(
        self,
        db: Session,
        builder: SmartRoutingPolicyBuilder | None = None,
    ) -> None:
        from app.repositories.smart_routing_rule import (
            SmartRoutingRuleRepository,
        )

        self.repository = SmartRoutingRuleRepository(db)
        self.builder = builder or SmartRoutingPolicyBuilder()

    def get_policy(self, user_id: int) -> TrafficRoutingPolicy:
        rules = self.repository.get_by_user(user_id)

        rule_data = tuple(
            SmartRoutingRuleData(
                target_type=rule.target_type,
                target=rule.target,
                action=rule.action,
                priority=rule.priority,
                address_family=rule.address_family,
                enabled=rule.enabled,
            )
            for rule in rules
        )

        return self.builder.build(rule_data)
