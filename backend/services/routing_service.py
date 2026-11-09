from __future__ import annotations

from backend.policy.context import PolicyContext
from backend.policy.engine import PolicyEngine
from backend.ports.server_repository import ServerRepository
from backend.services.server_selector import ServerSelector


class RoutingService:
    """
    Chooses the best available server.
    """

    def __init__(
        self,
        repository: ServerRepository,
        selector: ServerSelector,
        engine: PolicyEngine,
    ):
        self._repository = repository
        self._selector = selector
        self._engine = engine

    def select(self, context: PolicyContext):
        allowed = []

        for server in self._repository.get_available():
            context.server = server

            result = self._engine.execute(context)

            if result.allowed:
                allowed.append(server)

        return self._selector.select(allowed)
