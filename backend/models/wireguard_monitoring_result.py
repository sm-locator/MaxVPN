from __future__ import annotations

from dataclasses import dataclass

from backend.models.wireguard_health import WireGuardHealth
from backend.models.wireguard_monitor_state import WireGuardMonitorState


@dataclass(frozen=True, slots=True)
class WireGuardMonitoringResult:
    """
    Result of one WireGuard monitoring cycle.
    """

    health: WireGuardHealth
    state: WireGuardMonitorState
    recovery_required: bool
