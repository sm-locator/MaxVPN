from backend.models.server_metrics import ServerMetrics
from backend.services.metrics_repository import MetricsRepository
from backend.services.metrics_service import MetricsService
from tests.factories import make_server


def test_service_returns_metrics():
    metrics = ServerMetrics(
        cpu_load=20,
        latency=12,
    )

    service = MetricsService(
        MetricsRepository(),
    )

    server = make_server(metrics=metrics)

    assert service.metrics_for(server) is metrics


def test_service_returns_none():
    service = MetricsService(
        MetricsRepository(),
    )

    server = make_server(metrics=None)

    assert service.metrics_for(server) is None
