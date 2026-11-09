from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.models.traffic_routing_rule import (
    TrafficAddressFamily,
    TrafficRoute,
    TrafficRoutingRule,
    TrafficTargetType,
)
from backend.services.smart_routing_runtime_preview import (
    SmartRoutingRuntimePreviewService,
)


def test_build_separates_static_cidr_and_dynamic_domain_runtime() -> None:
    policy = TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="10.10.0.0/24",
                action=TrafficRoute.DIRECT,
                priority=100,
                address_family=TrafficAddressFamily.IPV4,
            ),
            TrafficRoutingRule(
                target_type=TrafficTargetType.DOMAIN,
                target="example.com",
                action=TrafficRoute.DIRECT,
                priority=200,
            ),
        ]
    )

    result = SmartRoutingRuntimePreviewService().build(policy)

    assert result.direct_ipv4_networks == ("10.10.0.0/24",)
    assert result.direct_domains == ("example.com",)


def test_vpn_rules_are_absent_from_desired_runtime() -> None:
    policy = TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="10.10.0.0/24",
                action=TrafficRoute.VPN,
                priority=100,
                address_family=TrafficAddressFamily.IPV4,
            ),
            TrafficRoutingRule(
                target_type=TrafficTargetType.DOMAIN,
                target="example.com",
                action=TrafficRoute.VPN,
                priority=200,
            ),
        ]
    )

    result = SmartRoutingRuntimePreviewService().build(policy)

    assert result.direct_ipv4_networks == ()
    assert result.direct_domains == ()


def test_higher_priority_vpn_removes_overlapping_direct_cidr() -> None:
    policy = TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="10.10.0.0/24",
                action=TrafficRoute.DIRECT,
                priority=100,
                address_family=TrafficAddressFamily.IPV4,
            ),
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="10.10.0.0/25",
                action=TrafficRoute.VPN,
                priority=200,
                address_family=TrafficAddressFamily.IPV4,
            ),
        ]
    )

    result = SmartRoutingRuntimePreviewService().build(policy)

    assert result.direct_ipv4_networks == ("10.10.0.128/25",)
