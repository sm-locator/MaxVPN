from __future__ import annotations

from typing import Protocol

from backend.models.maxvpn_installation import (
    InstallationPhase,
    InstallationStatus,
    InstallationStepResult,
    MaxVPNInstallationResult,
)


class InstallationAction(Protocol):
    def __call__(self) -> InstallationStepResult: ...


class RollbackAction(Protocol):
    def __call__(self) -> InstallationStepResult: ...


class InstallMaxVPNUseCase:
    """
    Orchestrates the production MaxVPN installation workflow.

    Each installation phase is injected as an action. This keeps the
    orchestration deterministic and independently testable.
    """

    PHASES = (
        InstallationPhase.PREFLIGHT,
        InstallationPhase.FIREWALL,
        InstallationPhase.WIREGUARD,
        InstallationPhase.MONITORING,
        InstallationPhase.FINAL_VERIFY,
    )

    def __init__(
        self,
        actions: dict[InstallationPhase, InstallationAction],
        rollback: RollbackAction,
    ) -> None:
        self._actions = actions
        self._rollback = rollback

    def execute(self) -> MaxVPNInstallationResult:
        steps: list[InstallationStepResult] = []

        for phase in self.PHASES:
            action = self._actions[phase]
            result = action()

            steps.append(result)

            if result.status == InstallationStatus.FAILED:
                rollback_result = self._rollback()
                steps.append(rollback_result)

                return MaxVPNInstallationResult(
                    status=InstallationStatus.FAILED,
                    completed_phase=InstallationPhase.ROLLBACK,
                    steps=tuple(steps),
                    reason=result.reason,
                )

            if result.status == InstallationStatus.DEGRADED:
                return MaxVPNInstallationResult(
                    status=InstallationStatus.DEGRADED,
                    completed_phase=phase,
                    steps=tuple(steps),
                    reason=result.reason,
                )

        return MaxVPNInstallationResult(
            status=InstallationStatus.SUCCESS,
            completed_phase=InstallationPhase.COMPLETE,
            steps=tuple(steps),
            reason=None,
        )
