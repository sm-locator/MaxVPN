from __future__ import annotations

from dataclasses import dataclass

from backend.models.wireguard_health import WireGuardHealthStatus
from backend.models.wireguard_recovery import (
    WireGuardRecoveryAction,
    WireGuardRecoveryPlan,
)


@dataclass(frozen=True, slots=True)
class WireGuardRecoveryPolicy:
    """
    Policy for deciding whether WireGuard recovery may be attempted.
    """

    max_attempts: int = 3
    backoff_seconds: tuple[int, ...] = (5, 15, 30)

    def plan(
        self,
        *,
        status: WireGuardHealthStatus,
        recovery_required: bool,
        attempt: int,
        reason: str | None,
    ) -> WireGuardRecoveryPlan:
        if not recovery_required:
            return WireGuardRecoveryPlan(
                action=WireGuardRecoveryAction.NONE,
                attempt=attempt,
                max_attempts=self.max_attempts,
                backoff_seconds=0,
                reason=reason,
            )

        if status is not WireGuardHealthStatus.FAILED:
            return WireGuardRecoveryPlan(
                action=WireGuardRecoveryAction.NONE,
                attempt=attempt,
                max_attempts=self.max_attempts,
                backoff_seconds=0,
                reason="recovery_requires_failed_state",
            )

        if attempt < 1:
            raise ValueError("Recovery attempt must be greater than or equal to 1.")

        if attempt > self.max_attempts:
            return WireGuardRecoveryPlan(
                action=WireGuardRecoveryAction.NONE,
                attempt=attempt,
                max_attempts=self.max_attempts,
                backoff_seconds=0,
                reason="max_attempts_exceeded",
            )

        backoff_index = min(
            attempt - 1,
            len(self.backoff_seconds) - 1,
        )

        return WireGuardRecoveryPlan(
            action=WireGuardRecoveryAction.RESTART_INTERFACE,
            attempt=attempt,
            max_attempts=self.max_attempts,
            backoff_seconds=self.backoff_seconds[backoff_index],
            reason=reason,
        )
