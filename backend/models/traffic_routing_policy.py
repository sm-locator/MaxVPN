from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from backend.models.traffic_routing_rule import (
    TrafficRoute,
    TrafficRoutingRule,
)


@dataclass(frozen=True, slots=True)
class TrafficRoutingDecision:
    action: TrafficRoute
    rule: TrafficRoutingRule | None = None


@dataclass(frozen=True, slots=True)
class TrafficRoutingPolicy:
    default_action: TrafficRoute = TrafficRoute.VPN
    rules: tuple[TrafficRoutingRule, ...] = ()

    @classmethod
    def from_rules(
        cls,
        rules: Iterable[TrafficRoutingRule],
        *,
        default_action: TrafficRoute = TrafficRoute.VPN,
    ) -> TrafficRoutingPolicy:
        normalized = tuple(rules)

        priorities = [rule.priority for rule in normalized if rule.enabled]

        if len(priorities) != len(set(priorities)):
            raise ValueError(
                "enabled routing rules must have unique priorities",
            )

        return cls(
            default_action=default_action,
            rules=normalized,
        )
