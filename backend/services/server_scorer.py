from __future__ import annotations

from backend.models.server import Server
from backend.services.server_score_weights import ServerScoreWeights


class ServerScorer:
    def __init__(
        self,
        weights: ServerScoreWeights | None = None,
    ):
        self._weights = weights or ServerScoreWeights()

    def score(self, server: Server) -> float:
        score = (
            100
            - server.load * self._weights.load
            - server.latency * self._weights.latency
        )

        return max(score, 0)
