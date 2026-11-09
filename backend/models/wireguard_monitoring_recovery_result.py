from __future__ import annotations

from dataclasses import dataclass

from backend.models.wireguard_monitoring_result import WireGuardMonitoringResult
from backend.models.wireguard_recovery import WireGuardRecoveryPlan
from backend.models.wireguard_recovery_result import WireGuardRecoveryResult


@dataclass(frozen=True, slots=True)
class WireGuardMonitoringRecoveryResult:
    """
    Result of one monitoring and optional recovery cycle.
    """

    monitoring: WireGuardMonitoringResult
    recovery_plan: WireGuardRecoveryPlan | None
    recovery: WireGuardRecoveryResult | None
