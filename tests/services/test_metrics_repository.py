from backend.models.server_metrics import ServerMetrics
from backend.services.in_memory_metrics_repository import InMemoryMetricsRepository
from tests.factories import make_server


def test_repository_returns_metrics():
    metrics = ServerMetrics(
        cpu_load=35,
        latency=12,
    )

    server = make_server(metrics=metrics)

    repository = InMemoryMetricsRepository()

    result = repository.get(server)

    assert result is metrics


def test_repository_returns_none_when_metrics_missing():
    server = make_server(metrics=None)

    repository = InMemoryMetricsRepository()

    assert repository.get(server) is None
