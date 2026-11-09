from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class InstallationPhase(str, Enum):
    PREFLIGHT = "preflight"
    FIREWALL = "firewall"
    WIREGUARD = "wireguard"
    MONITORING = "monitoring"
    FINAL_VERIFY = "final_verify"
    ROLLBACK = "rollback"
    COMPLETE = "complete"


class InstallationStatus(str, Enum):
    SUCCESS = "success"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class InstallationStepResult:
    phase: InstallationPhase
    status: InstallationStatus
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class MaxVPNInstallationResult:
    status: InstallationStatus
    completed_phase: InstallationPhase
    steps: tuple[InstallationStepResult, ...]
    reason: str | None = None

    @property
    def successful(self) -> bool:
        return self.status in {
            InstallationStatus.SUCCESS,
            InstallationStatus.DEGRADED,
        }
