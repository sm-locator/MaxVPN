from __future__ import annotations

from backend.models.server import Server
from backend.policy.context import PolicyContext
from backend.services.routing_service import RoutingService


class SelectBestServerUseCase:
    """
    Selects the best VPN server for a user.
    """

    def __init__(self, routing_service: RoutingService):
        self._routing_service = routing_service

    def execute(
        self,
        context: PolicyContext,
    ) -> Server | None:
        """
        Returns the best available server or None.
        """
        return self._routing_service.select(context)
