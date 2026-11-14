from backend.models.server import Server
from backend.services.server_selector import ServerSelector


def test_selector_returns_lowest_load():
    selector = ServerSelector()

    servers = [
        Server(
            1,
            "A",
            "PL",
            "Warsaw",
            "1.1.1.1:51820",
            "server-public-key-1",
            load=80,
        ),
        Server(
            2,
            "B",
            "DE",
            "Berlin",
            "2.2.2.2:51820",
            "server-public-key-2",
            load=20,
        ),
        Server(
            3,
            "C",
            "FR",
            "Paris",
            "3.3.3.3:51820",
            "server-public-key-3",
            load=60,
        ),
    ]

    best = selector.select(servers)

    assert best.id == 2


def test_selector_returns_none_when_empty():
    selector = ServerSelector()

    assert selector.select([]) is None
