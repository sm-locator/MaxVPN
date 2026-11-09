from __future__ import annotations

import time
from collections.abc import Callable

from backend.application.use_cases.check_wireguard_health import (
    CheckWireGuardHealthUseCase,
)
from backend.models.wireguard_health import WireGuardHealthStatus
from backend.models.wireguard_recovery import (
    WireGuardRecoveryAction,
    WireGuardRecoveryPlan,
)
from backend.models.wireguard_recovery_result import WireGuardRecoveryResult
from backend.ports.wireguard_recovery_executor import (
    WireGuardRecoveryExecutor,
)


class RecoverWireGuardUseCase:
    """
    Executes one WireGuard recovery attempt and verifies the result.
    """

    def __init__(
        self,
        recovery_executor: WireGuardRecoveryExecutor,
        health_check: CheckWireGuardHealthUseCase,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._recovery_executor = recovery_executor
        self._health_check = health_check
        self._sleeper = sleeper

    def execute(
        self,
        plan: WireGuardRecoveryPlan,
    ) -> WireGuardRecoveryResult:
        if plan.action is WireGuardRecoveryAction.NONE:
            health = self._health_check.execute()

            return WireGuardRecoveryResult(
                plan=plan,
                health=health,
                recovered=health.status is WireGuardHealthStatus.HEALTHY,
            )

        if plan.backoff_seconds > 0:
            self._sleeper(plan.backoff_seconds)

        self._recovery_executor.execute(plan)

        health = self._health_check.execute()

        return WireGuardRecoveryResult(
            plan=plan,
            health=health,
            recovered=health.status is WireGuardHealthStatus.HEALTHY,
        )
