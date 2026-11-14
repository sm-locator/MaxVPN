from __future__ import annotations

from backend.models.server import Server
from backend.models.server_metrics import ServerMetrics


class InMemoryMetricsRepository:
    """
    Temporary in-memory metrics repository.

    Later it will be replaced by a collector
    receiving metrics from VPN servers.
    """

    def get(self, server: Server) -> ServerMetrics | None:
        return server.metrics
