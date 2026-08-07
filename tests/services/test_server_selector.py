from backend.models.server import Server
from backend.services.server_selector import ServerSelector


def test_selector_returns_lowest_load():
    selector = ServerSelector()

    servers = [
        Server(1, "A", "PL", "Warsaw", load=80),
        Server(2, "B", "DE", "Berlin", load=20),
        Server(3, "C", "FR", "Paris", load=60),
    ]

    best = selector.select(servers)

    assert best.id == 2


def test_selector_returns_none_when_empty():
    selector = ServerSelector()

    assert selector.select([]) is None
