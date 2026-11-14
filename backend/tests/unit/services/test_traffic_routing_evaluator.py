import pytest
from backend.models.traffic_routing_policy import (
    TrafficRoutingPolicy,
)
from backend.models.traffic_routing_rule import (
    TrafficAddressFamily,
    TrafficRoute,
    TrafficRoutingRule,
    TrafficTargetType,
)
from backend.services.traffic_routing_evaluator import (
    TrafficRoutingEvaluator,
)


def test_default_route_is_vpn() -> None:
    policy = TrafficRoutingPolicy()

    decision = TrafficRoutingEvaluator().decide_domain(
        policy,
        "example.com",
    )

    assert decision.action is TrafficRoute.VPN
    assert decision.rule is None


def test_domain_rule_routes_exact_domain_direct() -> None:
    rule = TrafficRoutingRule(
        target_type=TrafficTargetType.DOMAIN,
        target="example.com",
        action=TrafficRoute.DIRECT,
        priority=100,
    )

    policy = TrafficRoutingPolicy.from_rules([rule])

    decision = TrafficRoutingEvaluator().decide_domain(
        policy,
        "example.com",
    )

    assert decision.action is TrafficRoute.DIRECT
    assert decision.rule == rule


def test_domain_rule_routes_subdomain_direct() -> None:
    rule = TrafficRoutingRule(
        target_type=TrafficTargetType.DOMAIN,
        target="example.com",
        action=TrafficRoute.DIRECT,
        priority=100,
    )

    policy = TrafficRoutingPolicy.from_rules([rule])

    decision = TrafficRoutingEvaluator().decide_domain(
        policy,
        "www.example.com",
    )

    assert decision.action is TrafficRoute.DIRECT
    assert decision.rule == rule


def test_domain_rule_does_not_match_unrelated_domain() -> None:
    rule = TrafficRoutingRule(
        target_type=TrafficTargetType.DOMAIN,
        target="example.com",
        action=TrafficRoute.DIRECT,
        priority=100,
    )

    policy = TrafficRoutingPolicy.from_rules([rule])

    decision = TrafficRoutingEvaluator().decide_domain(
        policy,
        "example.net",
    )

    assert decision.action is TrafficRoute.VPN
    assert decision.rule is None


def test_ipv4_cidr_rule_routes_direct() -> None:
    rule = TrafficRoutingRule(
        target_type=TrafficTargetType.CIDR,
        target="10.10.0.0/16",
        action=TrafficRoute.DIRECT,
        priority=100,
        address_family=TrafficAddressFamily.IPV4,
    )

    policy = TrafficRoutingPolicy.from_rules([rule])

    decision = TrafficRoutingEvaluator().decide_ip(
        policy,
        "10.10.20.5",
    )

    assert decision.action is TrafficRoute.DIRECT
    assert decision.rule == rule


def test_ipv6_cidr_rule_routes_direct() -> None:
    rule = TrafficRoutingRule(
        target_type=TrafficTargetType.CIDR,
        target="2001:db8::/32",
        action=TrafficRoute.DIRECT,
        priority=100,
        address_family=TrafficAddressFamily.IPV6,
    )

    policy = TrafficRoutingPolicy.from_rules([rule])

    decision = TrafficRoutingEvaluator().decide_ip(
        policy,
        "2001:db8:1234::10",
    )

    assert decision.action is TrafficRoute.DIRECT
    assert decision.rule == rule


def test_ipv4_rule_does_not_match_ipv6_address() -> None:
    rule = TrafficRoutingRule(
        target_type=TrafficTargetType.CIDR,
        target="10.10.0.0/16",
        action=TrafficRoute.DIRECT,
        priority=100,
        address_family=TrafficAddressFamily.IPV4,
    )

    policy = TrafficRoutingPolicy.from_rules([rule])

    decision = TrafficRoutingEvaluator().decide_ip(
        policy,
        "2001:db8::1",
    )

    assert decision.action is TrafficRoute.VPN


def test_higher_priority_rule_wins() -> None:
    vpn_rule = TrafficRoutingRule(
        target_type=TrafficTargetType.DOMAIN,
        target="example.com",
        action=TrafficRoute.VPN,
        priority=100,
    )

    direct_rule = TrafficRoutingRule(
        target_type=TrafficTargetType.DOMAIN,
        target="example.com",
        action=TrafficRoute.DIRECT,
        priority=200,
    )

    policy = TrafficRoutingPolicy.from_rules(
        [
            vpn_rule,
            direct_rule,
        ],
    )

    decision = TrafficRoutingEvaluator().decide_domain(
        policy,
        "example.com",
    )

    assert decision.action is TrafficRoute.DIRECT
    assert decision.rule == direct_rule


def test_disabled_rule_is_ignored() -> None:
    rule = TrafficRoutingRule(
        target_type=TrafficTargetType.DOMAIN,
        target="example.com",
        action=TrafficRoute.DIRECT,
        priority=100,
        enabled=False,
    )

    policy = TrafficRoutingPolicy.from_rules([rule])

    decision = TrafficRoutingEvaluator().decide_domain(
        policy,
        "example.com",
    )

    assert decision.action is TrafficRoute.VPN
    assert decision.rule is None


def test_duplicate_enabled_priorities_are_rejected() -> None:
    first = TrafficRoutingRule(
        target_type=TrafficTargetType.DOMAIN,
        target="example.com",
        action=TrafficRoute.DIRECT,
        priority=100,
    )

    second = TrafficRoutingRule(
        target_type=TrafficTargetType.DOMAIN,
        target="example.net",
        action=TrafficRoute.DIRECT,
        priority=100,
    )

    with pytest.raises(
        ValueError,
        match="unique priorities",
    ):
        TrafficRoutingPolicy.from_rules(
            [
                first,
                second,
            ],
        )


def test_domain_is_normalized() -> None:
    rule = TrafficRoutingRule(
        target_type=TrafficTargetType.DOMAIN,
        target="  Example.COM. ",
        action=TrafficRoute.DIRECT,
    )

    assert rule.target == "example.com"


def test_cidr_is_canonicalized() -> None:
    rule = TrafficRoutingRule(
        target_type=TrafficTargetType.CIDR,
        target="10.10.20.5/24",
        action=TrafficRoute.DIRECT,
    )

    assert rule.target == "10.10.20.0/24"
