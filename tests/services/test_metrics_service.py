from backend.models.server_metrics import ServerMetrics
from backend.services.in_memory_metrics_repository import InMemoryMetricsRepository
from backend.services.metrics_service import MetricsService
from tests.factories import make_server


def test_service_returns_metrics():
    metrics = ServerMetrics(
        cpu_load=20,
        latency=12,
    )

    service = MetricsService(
        InMemoryMetricsRepository(),
    )

    server = make_server(metrics=metrics)

    assert service.metrics_for(server) is metrics


def test_service_returns_none():
    service = MetricsService(
        InMemoryMetricsRepository(),
    )

    server = make_server(metrics=None)

    assert service.metrics_for(server) is None
