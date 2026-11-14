from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Callable

from backend.models.amneziawg_runtime_health import (
    AmneziaWGRuntimeHealth,
)


class AmneziaWGRuntimeHealthPolicy:
    """Interprets an AWG runtime snapshot without performing recovery."""

    def __init__(
        self,
        healthy_handshake_after: timedelta = timedelta(seconds=90),
        failed_handshake_after: timedelta = timedelta(seconds=300),
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._healthy_handshake_after = healthy_handshake_after
        self._failed_handshake_after = failed_handshake_after
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def evaluate(
        self,
        health: AmneziaWGRuntimeHealth,
    ) -> AmneziaWGRuntimeHealth:
        if not health.healthy:
            return health

        if health.latest_handshake is None:
            return replace(
                health,
                healthy=False,
                reason="no_handshake",
            )

        now = self._now_provider()
        age = now - health.latest_handshake

        if age < timedelta(0):
            age = timedelta(0)

        if age <= self._healthy_handshake_after:
            return health

        if age <= self._failed_handshake_after:
            # An older handshake is not by itself proof that the VPN is down.
            # Keep the runtime healthy while the existing runtime checks
            # (interface, peer, endpoint and route) remain valid.
            return health

        return replace(
            health,
            healthy=False,
            reason="handshake_timeout",
        )
