from unittest.mock import Mock

from backend.application.use_cases.apply_smart_routing import (
    ApplySmartRoutingUseCase,
)
from backend.infrastructure.openwrt.openwrt_traffic_routing import (
    OpenWrtTrafficRoutingResult,
)
from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.models.traffic_routing_rule import (
    TrafficRoute,
    TrafficRoutingRule,
    TrafficTargetType,
)


def make_policy() -> TrafficRoutingPolicy:
    return TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="1.1.1.1/32",
                action=TrafficRoute.DIRECT,
                priority=100,
            ),
        ]
    )


def make_result() -> OpenWrtTrafficRoutingResult:
    return OpenWrtTrafficRoutingResult(
        healthy=True,
        direct_ipset_exists=True,
        direct_rule_count=1,
        routing_table_exists=True,
        direct_route_exists=True,
    )


def test_execute_passes_explicit_policy_to_smart_routing_service() -> None:
    smart_routing = Mock()
    smart_routing.apply.return_value = make_result()

    policy_service = Mock()

    use_case = ApplySmartRoutingUseCase(
        smart_routing=smart_routing,
        policy_service=policy_service,
    )

    policy = make_policy()

    result = use_case.execute(policy)

    assert result.healthy is True
    smart_routing.apply.assert_called_once_with(policy)
    policy_service.get_policy.assert_not_called()


def test_execute_for_user_builds_policy_and_applies_it() -> None:
    smart_routing = Mock()
    smart_routing.apply.return_value = make_result()

    policy_service = Mock()
    policy = make_policy()
    policy_service.get_policy.return_value = policy

    use_case = ApplySmartRoutingUseCase(
        smart_routing=smart_routing,
        policy_service=policy_service,
    )

    result = use_case.execute_for_user(42)

    assert result.healthy is True
    policy_service.get_policy.assert_called_once_with(42)
    smart_routing.apply.assert_called_once_with(policy)
