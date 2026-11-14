from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Callable

from backend.infrastructure.wireguard.ssh_amneziawg_runtime_health import (
    SSHAmneziaWGRuntimeHealth,
)
from backend.models.amneziawg_config import AmneziaWGConfig
from backend.models.amneziawg_runtime_health import (
    AmneziaWGRuntimeHealth,
)
from backend.services.amneziawg_runtime_applier import (
    AmneziaWGRuntimeApplier,
    AmneziaWGRuntimeApplyResult,
)


@dataclass(frozen=True, slots=True)
class AmneziaWGRuntimeApplyVerificationResult:
    apply: AmneziaWGRuntimeApplyResult
    health: AmneziaWGRuntimeHealth | None
    verified: bool
    reason: str | None


class AmneziaWGRuntimeApplyVerifier:
    """
    Applies an AWG runtime configuration and then performs a
    read-only health verification.

    No recovery is performed.
    """

    def __init__(
        self,
        applier: AmneziaWGRuntimeApplier,
        health_checker: SSHAmneziaWGRuntimeHealth,
        wait_seconds: float = 15.0,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if wait_seconds < 0:
            raise ValueError("wait_seconds must not be negative")

        self._applier = applier
        self._health_checker = health_checker
        self._wait_seconds = wait_seconds
        self._sleeper = sleeper

    def execute(
        self,
        config: AmneziaWGConfig,
        interface: str = "WireGuard",
        runtime_path: str = "/tmp/maxvpn-awg-runtime.conf",
    ) -> AmneziaWGRuntimeApplyVerificationResult:
        apply_result = self._applier.apply(
            config=config,
            interface=interface,
            runtime_path=runtime_path,
        )

        if not apply_result.applied:
            return AmneziaWGRuntimeApplyVerificationResult(
                apply=apply_result,
                health=None,
                verified=False,
                reason=apply_result.reason or "awg_apply_failed",
            )

        if self._wait_seconds > 0:
            self._sleeper(self._wait_seconds)

        health = self._health_checker.check()

        if health.healthy:
            return AmneziaWGRuntimeApplyVerificationResult(
                apply=apply_result,
                health=health,
                verified=True,
                reason=None,
            )

        return AmneziaWGRuntimeApplyVerificationResult(
            apply=apply_result,
            health=health,
            verified=False,
            reason=health.reason or "awg_health_verification_failed",
        )
