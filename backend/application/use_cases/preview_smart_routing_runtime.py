from __future__ import annotations

from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.services.smart_routing_policy_service import (
    SmartRoutingPolicyService,
)
from backend.services.smart_routing_runtime_plan import (
    SmartRoutingRuntimePlan,
    SmartRoutingRuntimePlanService,
)


class PreviewSmartRoutingRuntimeUseCase:
    """
    Builds a read-only Smart Routing runtime plan.

    No OpenWrt state is modified.
    """

    def __init__(
        self,
        plan_service: SmartRoutingRuntimePlanService,
        policy_service: SmartRoutingPolicyService,
    ) -> None:
        self._plan_service = plan_service
        self._policy_service = policy_service

    def execute(
        self,
        policy: TrafficRoutingPolicy,
    ) -> SmartRoutingRuntimePlan:
        return self._plan_service.build(policy)

    def execute_for_user(
        self,
        user_id: int,
    ) -> SmartRoutingRuntimePlan:
        policy = self._policy_service.get_policy(user_id)
        return self.execute(policy)
