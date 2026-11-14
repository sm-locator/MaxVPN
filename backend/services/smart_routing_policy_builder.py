from __future__ import annotations

from collections.abc import Sequence

from backend.models.smart_routing_rule_data import SmartRoutingRuleData
from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.models.traffic_routing_rule import (
    TrafficAddressFamily,
    TrafficRoute,
    TrafficRoutingRule,
    TrafficTargetType,
)


class SmartRoutingPolicyBuilder:
    def build(
        self,
        rules: Sequence[SmartRoutingRuleData],
    ) -> TrafficRoutingPolicy:
        domain_rules = tuple(self._to_domain_rule(rule) for rule in rules)

        return TrafficRoutingPolicy.from_rules(domain_rules)

    @staticmethod
    def _to_domain_rule(
        rule: SmartRoutingRuleData,
    ) -> TrafficRoutingRule:
        return TrafficRoutingRule(
            target_type=TrafficTargetType(rule.target_type),
            target=rule.target,
            action=TrafficRoute(rule.action),
            priority=rule.priority,
            address_family=TrafficAddressFamily(rule.address_family),
            enabled=rule.enabled,
        )
