from backend.models.server import Server
from backend.services.server_repository import ServerRepository


def test_repository_returns_all_servers():
    repo = ServerRepository(
        [
            Server(1, "A", "PL", "Warsaw"),
            Server(2, "B", "DE", "Berlin"),
        ]
    )

    assert len(repo.all()) == 2


def test_repository_returns_only_online_servers():
    repo = ServerRepository(
        [
            Server(1, "A", "PL", "Warsaw", online=True),
            Server(2, "B", "DE", "Berlin", online=False),
        ]
    )

    assert len(repo.online()) == 1
