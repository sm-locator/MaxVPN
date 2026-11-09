import pytest
from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.models.traffic_routing_rule import (
    TrafficRoute,
    TrafficRoutingRule,
    TrafficTargetType,
)
from backend.services.domain_routing_runtime_compiler import (
    DomainRoutingCompileError,
    DomainRoutingRuntimeCompiler,
)


def make_rule(
    *,
    domain: str,
    action: TrafficRoute,
    priority: int,
) -> TrafficRoutingRule:
    return TrafficRoutingRule(
        target_type=TrafficTargetType.DOMAIN,
        target=domain,
        action=action,
        priority=priority,
    )


def test_compile_returns_direct_domains() -> None:
    policy = TrafficRoutingPolicy.from_rules(
        [
            make_rule(
                domain="example.net",
                action=TrafficRoute.DIRECT,
                priority=200,
            ),
            make_rule(
                domain="example.com",
                action=TrafficRoute.DIRECT,
                priority=100,
            ),
        ]
    )

    result = DomainRoutingRuntimeCompiler().compile(policy)

    assert result.direct_domains == (
        "example.net",
        "example.com",
    )


def test_vpn_domain_is_not_added_to_direct_domains() -> None:
    policy = TrafficRoutingPolicy.from_rules(
        [
            make_rule(
                domain="example.com",
                action=TrafficRoute.VPN,
                priority=100,
            ),
        ]
    )

    result = DomainRoutingRuntimeCompiler().compile(policy)

    assert result.direct_domains == ()


def test_same_action_parent_and_child_are_allowed() -> None:
    policy = TrafficRoutingPolicy.from_rules(
        [
            make_rule(
                domain="example.com",
                action=TrafficRoute.DIRECT,
                priority=100,
            ),
            make_rule(
                domain="api.example.com",
                action=TrafficRoute.DIRECT,
                priority=200,
            ),
        ]
    )

    result = DomainRoutingRuntimeCompiler().compile(policy)

    assert result.direct_domains == (
        "api.example.com",
        "example.com",
    )


def test_direct_parent_and_vpn_child_are_rejected() -> None:
    policy = TrafficRoutingPolicy.from_rules(
        [
            make_rule(
                domain="example.com",
                action=TrafficRoute.DIRECT,
                priority=100,
            ),
            make_rule(
                domain="api.example.com",
                action=TrafficRoute.VPN,
                priority=200,
            ),
        ]
    )

    with pytest.raises(
        DomainRoutingCompileError,
        match="conflicting domain routing rules",
    ):
        DomainRoutingRuntimeCompiler().compile(policy)


def test_vpn_parent_and_direct_child_are_rejected() -> None:
    policy = TrafficRoutingPolicy.from_rules(
        [
            make_rule(
                domain="example.com",
                action=TrafficRoute.VPN,
                priority=200,
            ),
            make_rule(
                domain="api.example.com",
                action=TrafficRoute.DIRECT,
                priority=100,
            ),
        ]
    )

    with pytest.raises(
        DomainRoutingCompileError,
        match="conflicting domain routing rules",
    ):
        DomainRoutingRuntimeCompiler().compile(policy)


def test_exact_same_domain_with_different_actions_is_rejected() -> None:
    policy = TrafficRoutingPolicy.from_rules(
        [
            make_rule(
                domain="example.com",
                action=TrafficRoute.DIRECT,
                priority=100,
            ),
            make_rule(
                domain="example.com",
                action=TrafficRoute.VPN,
                priority=200,
            ),
        ]
    )

    with pytest.raises(
        DomainRoutingCompileError,
        match="conflicting domain routing rules",
    ):
        DomainRoutingRuntimeCompiler().compile(policy)
