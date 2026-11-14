from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from backend.models.wireguard_health import WireGuardHealthStatus
from backend.models.wireguard_monitor_state import WireGuardMonitorState


@dataclass(frozen=True, slots=True)
class WireGuardMonitorThresholds:
    """
    Thresholds for transitioning monitoring state.
    """

    degraded_to_failed_checks: int = 3
    failed_to_recovered_checks: int = 1


class WireGuardMonitor:
    """
    Maintains monitoring state across health-check snapshots.
    """

    def __init__(
        self,
        thresholds: WireGuardMonitorThresholds | None = None,
    ) -> None:
        self._thresholds = thresholds or WireGuardMonitorThresholds()
        self._state: WireGuardMonitorState | None = None

    @property
    def state(self) -> WireGuardMonitorState | None:
        return self._state

    def update(
        self,
        status: WireGuardHealthStatus,
        checked_at: datetime | None = None,
    ) -> WireGuardMonitorState:
        now = checked_at or datetime.now(timezone.utc)

        if self._state is None:
            self._state = WireGuardMonitorState(
                status=status,
                consecutive_failures=1 if status is WireGuardHealthStatus.FAILED else 0,
                consecutive_degraded=(
                    1 if status is WireGuardHealthStatus.DEGRADED else 0
                ),
                last_status_change=now,
                last_check_at=now,
            )
            return self._state

        previous = self._state

        consecutive_failures = (
            previous.consecutive_failures + 1
            if status is WireGuardHealthStatus.FAILED
            else 0
        )

        consecutive_degraded = (
            previous.consecutive_degraded + 1
            if status is WireGuardHealthStatus.DEGRADED
            else 0
        )

        effective_status = status

        if (
            status is WireGuardHealthStatus.DEGRADED
            and consecutive_degraded >= self._thresholds.degraded_to_failed_checks
        ):
            effective_status = WireGuardHealthStatus.FAILED

        if status is WireGuardHealthStatus.HEALTHY:
            consecutive_failures = 0
            consecutive_degraded = 0

        status_changed = effective_status is not previous.status

        self._state = WireGuardMonitorState(
            status=effective_status,
            consecutive_failures=consecutive_failures,
            consecutive_degraded=consecutive_degraded,
            last_status_change=(now if status_changed else previous.last_status_change),
            last_check_at=now,
        )

        return self._state

    def reset(self) -> None:
        self._state = None
