from __future__ import annotations

from backend.models.wireguard_health import WireGuardHealth
from backend.ports.wireguard_health_checker import WireGuardHealthChecker
from backend.services.wireguard_health_policy import WireGuardHealthPolicy


class CheckWireGuardHealthUseCase:
    """
    Checks WireGuard runtime state and evaluates its health policy.
    """

    def __init__(
        self,
        health_checker: WireGuardHealthChecker,
        health_policy: WireGuardHealthPolicy,
    ) -> None:
        self._health_checker = health_checker
        self._health_policy = health_policy

    def execute(self) -> WireGuardHealth:
        health = self._health_checker.check()
        return self._health_policy.evaluate(health)
