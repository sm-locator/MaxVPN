import pytest

from backend.models.smart_routing_rule_data import SmartRoutingRuleData
from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.models.traffic_routing_rule import (
    TrafficAddressFamily,
    TrafficRoute,
    TrafficTargetType,
)
from backend.services.smart_routing_policy_builder import (
    SmartRoutingPolicyBuilder,
)


def make_rule(
    *,
    target_type: str = "cidr",
    target: str = "1.1.1.0/24",
    action: str = "direct",
    priority: int = 100,
    address_family: str = "ipv4",
    enabled: bool = True,
) -> SmartRoutingRuleData:
    return SmartRoutingRuleData(
        target_type=target_type,
        target=target,
        action=action,
        priority=priority,
        address_family=address_family,
        enabled=enabled,
    )


def test_build_empty_policy_defaults_to_vpn() -> None:
    policy = SmartRoutingPolicyBuilder().build([])

    assert isinstance(policy, TrafficRoutingPolicy)
    assert policy.default_action is TrafficRoute.VPN
    assert policy.rules == ()


def test_build_converts_cidr_direct_rule() -> None:
    policy = SmartRoutingPolicyBuilder().build(
        [
            make_rule(
                target_type="cidr",
                target="1.1.1.17/24",
                action="direct",
                priority=200,
                address_family="ipv4",
            )
        ]
    )

    rule = policy.rules[0]

    assert rule.target_type is TrafficTargetType.CIDR
    assert rule.target == "1.1.1.0/24"
    assert rule.action is TrafficRoute.DIRECT
    assert rule.priority == 200
    assert rule.address_family is TrafficAddressFamily.IPV4
    assert rule.enabled is True


def test_build_converts_domain_vpn_rule() -> None:
    policy = SmartRoutingPolicyBuilder().build(
        [
            make_rule(
                target_type="domain",
                target="Example.COM.",
                action="vpn",
                priority=50,
                address_family="any",
            )
        ]
    )

    rule = policy.rules[0]

    assert rule.target_type is TrafficTargetType.DOMAIN
    assert rule.target == "example.com"
    assert rule.action is TrafficRoute.VPN
    assert rule.priority == 50
    assert rule.address_family is TrafficAddressFamily.ANY


def test_build_preserves_disabled_rules() -> None:
    policy = SmartRoutingPolicyBuilder().build(
        [
            make_rule(
                priority=100,
                enabled=False,
            )
        ]
    )

    assert policy.rules[0].enabled is False


def test_build_rejects_duplicate_enabled_priorities() -> None:
    with pytest.raises(
        ValueError,
        match="enabled routing rules must have unique priorities",
    ):
        SmartRoutingPolicyBuilder().build(
            [
                make_rule(priority=100),
                make_rule(
                    target="2.2.2.0/24",
                    priority=100,
                ),
            ]
        )


def test_build_accepts_duplicate_priorities_when_one_rule_disabled() -> None:
    policy = SmartRoutingPolicyBuilder().build(
        [
            make_rule(priority=100),
            make_rule(
                target="2.2.2.0/24",
                priority=100,
                enabled=False,
            ),
        ]
    )

    assert len(policy.rules) == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_type", "invalid"),
        ("action", "invalid"),
        ("address_family", "invalid"),
    ],
)
def test_build_rejects_invalid_enum_values(
    field: str,
    value: str,
) -> None:
    kwargs = {
        "target_type": "cidr",
        "target": "1.1.1.0/24",
        "action": "direct",
        "priority": 100,
        "address_family": "ipv4",
        "enabled": True,
    }
    kwargs[field] = value

    rule = SmartRoutingRuleData(**kwargs)

    with pytest.raises(ValueError):
        SmartRoutingPolicyBuilder().build([rule])
