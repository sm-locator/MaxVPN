from backend.models.server import Server
from backend.services.in_memory_server_repository import (
    InMemoryServerRepository,
)


def test_repository_returns_all_servers():
    repo = InMemoryServerRepository(
        [
            Server(
                1,
                "A",
                "PL",
                "Warsaw",
                "1.1.1.1:51820",
                "server-public-key-1",
            ),
            Server(
                2,
                "B",
                "DE",
                "Berlin",
                "2.2.2.2:51820",
                "server-public-key-2",
            ),
        ]
    )

    assert len(repo.get_all()) == 2


def test_repository_returns_only_online_servers():
    repo = InMemoryServerRepository(
        [
            Server(
                1,
                "A",
                "PL",
                "Warsaw",
                "1.1.1.1:51820",
                "server-public-key-1",
                online=True,
            ),
            Server(
                2,
                "B",
                "DE",
                "Berlin",
                "2.2.2.2:51820",
                "server-public-key-2",
                online=False,
            ),
        ]
    )

    available = repo.get_available()

    assert len(available) == 1
    assert available[0].online is True
