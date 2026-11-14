from unittest.mock import Mock

from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.models.traffic_routing_rule import (
    TrafficRoute,
    TrafficRoutingRule,
    TrafficTargetType,
)
from backend.services.domain_routing_resolver import DomainRoutingResolver
from backend.services.domain_routing_service import DomainRoutingService
from backend.services.traffic_routing_evaluator import TrafficRoutingEvaluator


def make_policy(action: TrafficRoute) -> TrafficRoutingPolicy:
    return TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.DOMAIN,
                target="example.com",
                action=action,
                priority=100,
            )
        ]
    )


def test_direct_domain_is_resolved() -> None:
    resolver = Mock(spec=DomainRoutingResolver)
    resolver.resolve.return_value = (
        "2001:db8::10",
        "192.0.2.20",
        "192.0.2.10",
    )

    evaluator = Mock(spec=TrafficRoutingEvaluator)
    evaluator.decide_domain.return_value = evaluator_decision(TrafficRoute.DIRECT)

    service = DomainRoutingService(
        resolver=resolver,
        evaluator=evaluator,
    )

    result = service.resolve(
        make_policy(TrafficRoute.DIRECT),
        "  Example.COM. ",
    )

    assert result.domain == "example.com"
    assert result.decision.action is TrafficRoute.DIRECT
    assert result.ipv4_addresses == (
        "192.0.2.10",
        "192.0.2.20",
    )

    resolver.resolve.assert_called_once_with("  Example.COM. ")
    evaluator.decide_domain.assert_called_once_with(
        make_policy(TrafficRoute.DIRECT),
        "  Example.COM. ",
    )


def test_vpn_domain_is_not_resolved() -> None:
    resolver = Mock(spec=DomainRoutingResolver)
    evaluator = Mock(spec=TrafficRoutingEvaluator)
    evaluator.decide_domain.return_value = evaluator_decision(TrafficRoute.VPN)

    service = DomainRoutingService(
        resolver=resolver,
        evaluator=evaluator,
    )

    result = service.resolve(
        make_policy(TrafficRoute.VPN),
        "example.com",
    )

    assert result.domain == "example.com"
    assert result.decision.action is TrafficRoute.VPN
    assert result.ipv4_addresses == ()

    resolver.resolve.assert_not_called()


def test_direct_domain_with_only_ipv6_returns_no_ipv4_addresses() -> None:
    resolver = Mock(spec=DomainRoutingResolver)
    resolver.resolve.return_value = ("2001:db8::10",)

    evaluator = Mock(spec=TrafficRoutingEvaluator)
    evaluator.decide_domain.return_value = evaluator_decision(TrafficRoute.DIRECT)

    service = DomainRoutingService(
        resolver=resolver,
        evaluator=evaluator,
    )

    result = service.resolve(
        make_policy(TrafficRoute.DIRECT),
        "example.com",
    )

    assert result.ipv4_addresses == ()


def evaluator_decision(action: TrafficRoute):
    return Mock(
        action=action,
        rule=None,
    )
