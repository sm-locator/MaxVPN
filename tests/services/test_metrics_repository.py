from backend.services.metrics_repository import MetricsRepository
from backend.models.server_metrics import ServerMetrics
from tests.factories import make_server


def test_repository_returns_metrics():
    metrics = ServerMetrics(
        cpu_load=35,
        latency=12,
    )

    server = make_server(metrics=metrics)

    repository = MetricsRepository()

    result = repository.get(server)

    assert result is metrics


def test_repository_returns_none_when_metrics_missing():
    server = make_server(metrics=None)

    repository = MetricsRepository()

    assert repository.get(server) is None
