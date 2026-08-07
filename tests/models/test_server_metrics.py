from backend.models.server_metrics import ServerMetrics


def test_metrics_defaults():
    metrics = ServerMetrics()

    assert metrics.cpu_load == 0
    assert metrics.latency == 0
    assert metrics.packet_loss == 0
    assert metrics.active_clients == 0


def test_metrics_can_store_values():
    metrics = ServerMetrics(
        cpu_load=25,
        latency=18,
        packet_loss=0.2,
        active_clients=143,
    )

    assert metrics.cpu_load == 25
    assert metrics.latency == 18
    assert metrics.packet_loss == 0.2
    assert metrics.active_clients == 143
