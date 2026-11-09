from __future__ import annotations

from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.services.smart_routing_policy_service import (
    SmartRoutingPolicyService,
)
from backend.services.smart_routing_service import SmartRoutingService


class ApplySmartRoutingUseCase:
    """
    Applies Smart Routing policy to OpenWrt.

    The policy may be supplied explicitly or built from persisted
    rules for a specific user.
    """

    def __init__(
        self,
        smart_routing: SmartRoutingService,
        policy_service: SmartRoutingPolicyService,
    ) -> None:
        self._smart_routing = smart_routing
        self._policy_service = policy_service

    def execute(
        self,
        policy: TrafficRoutingPolicy,
    ):
        return self._smart_routing.apply(policy)

    def execute_for_user(
        self,
        user_id: int,
    ):
        policy = self._policy_service.get_policy(user_id)

        return self.execute(policy)
