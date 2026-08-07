from __future__ import annotations

from backend.models.server import Server
from backend.models.server_metrics import ServerMetrics
from backend.services.metrics_repository import MetricsRepository


class MetricsService:
    """
    High-level access to server metrics.
    """

    def __init__(
        self,
        repository: MetricsRepository,
    ):
        self._repository = repository

    def metrics_for(
        self,
        server: Server,
    ) -> ServerMetrics | None:
        return self._repository.get(server)
