from __future__ import annotations

from backend.models.server import Server
from backend.services.server_scorer import ServerScorer


class ServerSelector:
    """
    Chooses the highest-scoring server.
    """

    def __init__(self):
        self._scorer = ServerScorer()

    def select(self, servers: list[Server]) -> Server | None:
        if not servers:
            return None

        return max(
            servers,
            key=self._scorer.score,
        )
