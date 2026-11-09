from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WireGuardRecoveryAction(str, Enum):
    NONE = "none"
    RESTART_INTERFACE = "restart_interface"


@dataclass(frozen=True, slots=True)
class WireGuardRecoveryPlan:
    """
    Plan for recovering an unhealthy WireGuard runtime.
    """

    action: WireGuardRecoveryAction
    attempt: int
    max_attempts: int
    backoff_seconds: int
    reason: str | None = None
