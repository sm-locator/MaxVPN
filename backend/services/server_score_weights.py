from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ServerScoreWeights:
    """
    Weight coefficients used by ServerScorer.
    """

    load: float = 1.0
    latency: float = 0.1
    reliability: float = 0.0
    premium_bonus: float = 0.0
    geo_bonus: float = 0.0
