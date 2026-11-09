from unittest.mock import Mock, patch

from backend.models.smart_routing_rule_data import SmartRoutingRuleData
from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.models.traffic_routing_rule import TrafficRoute
from backend.services.smart_routing_policy_builder import (
    SmartRoutingPolicyBuilder,
)
from backend.services.smart_routing_policy_service import (
    SmartRoutingPolicyService,
)


def make_rule(
    *,
    user_id: int,
    target: str,
    action: str = "direct",
    priority: int = 100,
    enabled: bool = True,
):
    rule = Mock()
    rule.user_id = user_id
    rule.target_type = "cidr"
    rule.target = target
    rule.action = action
    rule.priority = priority
    rule.address_family = "ipv4"
    rule.enabled = enabled
    return rule


def make_repository(rules):
    repository = Mock()
    repository.get_by_user.return_value = rules
    return repository


def test_get_policy_loads_only_requested_user_rules() -> None:
    rules = [
        make_rule(
            user_id=1,
            target="1.1.1.0/24",
        )
    ]

    repository = make_repository(rules)
    builder = SmartRoutingPolicyBuilder()

    with patch(
        "app.repositories.smart_routing_rule.SmartRoutingRuleRepository",
        return_value=repository,
    ):
        service = SmartRoutingPolicyService(
            Mock(),
            builder=builder,
        )

    policy = service.get_policy(1)

    assert isinstance(policy, TrafficRoutingPolicy)
    assert len(policy.rules) == 1
    assert policy.rules[0].target == "1.1.1.0/24"
    assert policy.rules[0].action is TrafficRoute.DIRECT
    repository.get_by_user.assert_called_once_with(1)


def test_get_policy_returns_default_vpn_when_user_has_no_rules() -> None:
    repository = make_repository([])
    builder = Mock(spec=SmartRoutingPolicyBuilder)

    expected = TrafficRoutingPolicy()

    builder.build.return_value = expected

    with patch(
        "app.repositories.smart_routing_rule.SmartRoutingRuleRepository",
        return_value=repository,
    ):
        service = SmartRoutingPolicyService(
            Mock(),
            builder=builder,
        )

    policy = service.get_policy(1)

    assert policy is expected
    repository.get_by_user.assert_called_once_with(1)
    builder.build.assert_called_once_with(())


def test_get_policy_converts_persisted_rules_to_builder_data() -> None:
    rules = [
        make_rule(
            user_id=1,
            target="1.1.1.0/24",
            priority=200,
        )
    ]

    repository = make_repository(rules)
    builder = Mock(spec=SmartRoutingPolicyBuilder)
    expected = TrafficRoutingPolicy()
    builder.build.return_value = expected

    with patch(
        "app.repositories.smart_routing_rule.SmartRoutingRuleRepository",
        return_value=repository,
    ):
        service = SmartRoutingPolicyService(
            Mock(),
            builder=builder,
        )

    result = service.get_policy(1)

    assert result is expected

    builder.build.assert_called_once()

    data = builder.build.call_args.args[0]

    assert data == (
        SmartRoutingRuleData(
            target_type="cidr",
            target="1.1.1.0/24",
            action="direct",
            priority=200,
            address_family="ipv4",
            enabled=True,
        ),
    )
