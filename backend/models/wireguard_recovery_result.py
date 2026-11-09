from __future__ import annotations

from dataclasses import dataclass

from backend.models.wireguard_health import WireGuardHealth
from backend.models.wireguard_recovery import WireGuardRecoveryPlan


@dataclass(frozen=True, slots=True)
class WireGuardRecoveryResult:
    """
    Result of a WireGuard recovery attempt.
    """

    plan: WireGuardRecoveryPlan
    health: WireGuardHealth
    recovered: bool
