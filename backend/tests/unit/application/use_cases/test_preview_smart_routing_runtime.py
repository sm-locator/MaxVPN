from unittest.mock import Mock

from backend.application.use_cases.preview_smart_routing_runtime import (
    PreviewSmartRoutingRuntimeUseCase,
)
from backend.services.smart_routing_runtime_plan import (
    SmartRoutingRuntimePlan,
)


def test_execute_delegates_to_plan_service() -> None:
    plan_service = Mock()
    policy_service = Mock()

    policy = Mock()
    plan = Mock(spec=SmartRoutingRuntimePlan)

    plan_service.build.return_value = plan

    use_case = PreviewSmartRoutingRuntimeUseCase(
        plan_service=plan_service,
        policy_service=policy_service,
    )

    result = use_case.execute(policy)

    assert result is plan
    plan_service.build.assert_called_once_with(policy)
    policy_service.get_policy.assert_not_called()


def test_execute_for_user_builds_plan_from_user_policy() -> None:
    plan_service = Mock()
    policy_service = Mock()

    policy = Mock()
    plan = Mock(spec=SmartRoutingRuntimePlan)

    policy_service.get_policy.return_value = policy
    plan_service.build.return_value = plan

    use_case = PreviewSmartRoutingRuntimeUseCase(
        plan_service=plan_service,
        policy_service=policy_service,
    )

    result = use_case.execute_for_user(42)

    assert result is plan
    policy_service.get_policy.assert_called_once_with(42)
    plan_service.build.assert_called_once_with(policy)
