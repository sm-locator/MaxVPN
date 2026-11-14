from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Callable

from backend.infrastructure.wireguard.ssh_amneziawg_runtime_health import (
    SSHAmneziaWGRuntimeHealth,
)
from backend.models.amneziawg_config import AmneziaWGConfig
from backend.ports.amneziawg_runtime_snapshot import (
    AmneziaWGRuntimeSnapshotPort,
)
from backend.ports.wireguard_interface_lifecycle import (
    WireGuardInterfaceLifecycle,
)
from backend.services.amneziawg_runtime_applier import (
    AmneziaWGRuntimeApplier,
)


@dataclass(frozen=True, slots=True)
class AmneziaWGRuntimeManagerResult:
    applied: bool
    verified: bool
    rolled_back: bool
    rollback_verified: bool
    health_failed: bool
    reason: str | None
    no_change: bool = False


class AmneziaWGRuntimeManager:
    """
    Safely applies an AmneziaWG runtime configuration.

    Transaction:

        capture current runtime
        -> apply new config
        -> verify health
        -> success

    or:

        capture current runtime
        -> apply new config
        -> verify health failed
        -> restore snapshot
        -> verify restored health

    The manager does not perform interface lifecycle operations.
    """

    def __init__(
        self,
        applier: AmneziaWGRuntimeApplier,
        snapshot: AmneziaWGRuntimeSnapshotPort,
        health_checker: SSHAmneziaWGRuntimeHealth,
        lifecycle: WireGuardInterfaceLifecycle,
        wait_seconds: float = 15.0,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if wait_seconds < 0:
            raise ValueError("wait_seconds must not be negative")

        self._applier = applier
        self._snapshot = snapshot
        self._health_checker = health_checker
        self._lifecycle = lifecycle
        self._wait_seconds = wait_seconds
        self._sleeper = sleeper

    def apply(
        self,
        config: AmneziaWGConfig,
        interface: str = "WireGuard",
        runtime_path: str = "/tmp/maxvpn-awg-runtime.conf",
    ) -> AmneziaWGRuntimeManagerResult:
        was_present = self._lifecycle.exists(interface)
        brought_up = False

        if not was_present:
            try:
                self._lifecycle.bring_up(interface)
                brought_up = True
            except Exception as exc:
                return AmneziaWGRuntimeManagerResult(
                    applied=False,
                    verified=False,
                    rolled_back=False,
                    rollback_verified=False,
                    health_failed=False,
                    reason=f"interface_start_failed: {exc}",
                )

        try:
            previous = self._snapshot.capture(interface)
        except Exception as exc:
            if brought_up:
                try:
                    self._lifecycle.bring_down(interface)
                except Exception:
                    pass

            return AmneziaWGRuntimeManagerResult(
                applied=False,
                verified=False,
                rolled_back=False,
                rollback_verified=False,
                health_failed=False,
                reason=f"snapshot_capture_failed: {exc}",
            )

        apply_result = self._applier.apply(
            config=config,
            interface=interface,
            runtime_path=runtime_path,
        )

        if not apply_result.applied:
            if brought_up:
                try:
                    self._lifecycle.bring_down(interface)
                except Exception:
                    pass

            return AmneziaWGRuntimeManagerResult(
                applied=False,
                verified=False,
                rolled_back=False,
                rollback_verified=False,
                health_failed=False,
                reason=apply_result.reason or "awg_apply_failed",
            )

        health = self._verify_after_wait()

        if health.healthy:
            return AmneziaWGRuntimeManagerResult(
                applied=True,
                verified=True,
                rolled_back=False,
                rollback_verified=False,
                health_failed=False,
                reason=None,
            )

        health_reason = health.reason or "awg_health_verification_failed"

        try:
            self._snapshot.restore(previous)
        except Exception as exc:
            return AmneziaWGRuntimeManagerResult(
                applied=True,
                verified=False,
                rolled_back=True,
                rollback_verified=False,
                health_failed=True,
                reason=(
                    f"awg_health_verification_failed: {health_reason}; "
                    f"rollback_failed: {exc}"
                ),
            )

        rollback_health = self._health_checker.check()

        if brought_up:
            try:
                self._lifecycle.bring_down(interface)
            except Exception as exc:
                return AmneziaWGRuntimeManagerResult(
                    applied=True,
                    verified=False,
                    rolled_back=True,
                    rollback_verified=False,
                    health_failed=True,
                    reason=(
                        f"awg_health_verification_failed: {health_reason}; "
                        f"interface_shutdown_failed: {exc}"
                    ),
                )

            return AmneziaWGRuntimeManagerResult(
                applied=True,
                verified=False,
                rolled_back=True,
                rollback_verified=True,
                health_failed=True,
                reason=(
                    f"awg_health_verification_failed: {health_reason}; "
                    "interface_restored_down"
                ),
            )

        if rollback_health.healthy:
            return AmneziaWGRuntimeManagerResult(
                applied=True,
                verified=False,
                rolled_back=True,
                rollback_verified=True,
                health_failed=True,
                reason=f"awg_health_verification_failed: {health_reason}",
            )

        rollback_reason = (
            rollback_health.reason or "awg_rollback_health_verification_failed"
        )

        return AmneziaWGRuntimeManagerResult(
            applied=True,
            verified=False,
            rolled_back=True,
            rollback_verified=False,
            health_failed=True,
            reason=(
                f"awg_health_verification_failed: {health_reason}; "
                f"rollback_health_failed: {rollback_reason}"
            ),
        )

    def _verify_after_wait(self):
        if self._wait_seconds > 0:
            self._sleeper(self._wait_seconds)

        return self._health_checker.check()
