from __future__ import annotations

from dataclasses import dataclass

from backend.models.amneziawg_config import AmneziaWGConfig
from backend.ports.remote_command_executor import RemoteCommandExecutor
from backend.services.amneziawg_config_renderer import (
    AmneziaWGConfigRenderer,
)


@dataclass(frozen=True, slots=True)
class AmneziaWGRuntimePlan:
    interface: str
    runtime_path: str
    runtime_config: str
    upload_command: tuple[str, ...]
    sync_command: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AmneziaWGRuntimeApplyResult:
    plan: AmneziaWGRuntimePlan
    upload_returncode: int
    sync_returncode: int | None
    uploaded: bool
    applied: bool
    reason: str | None = None


class AmneziaWGRuntimeApplier:
    """
    Plans and optionally applies a complete AmneziaWG runtime config.

    The service does not perform interface lifecycle operations:
    no ifdown, ifup, network reload, firewall reload, or reboot.
    """

    def __init__(
        self,
        renderer: AmneziaWGConfigRenderer | None = None,
        command_executor: RemoteCommandExecutor | None = None,
    ) -> None:
        self._renderer = renderer or AmneziaWGConfigRenderer()
        self._command_executor = command_executor

    def plan(
        self,
        config: AmneziaWGConfig,
        interface: str = "WireGuard",
        runtime_path: str = "/tmp/maxvpn-awg-runtime.conf",
    ) -> AmneziaWGRuntimePlan:
        if not interface:
            raise ValueError("interface must not be empty")

        if not runtime_path:
            raise ValueError("runtime_path must not be empty")

        runtime_config = self._renderer.render_awg_runtime(config)

        upload_command = (
            "sh",
            "-c",
            f"cat > {runtime_path} && chmod 600 {runtime_path}",
        )

        sync_command = (
            "awg",
            "syncconf",
            interface,
            runtime_path,
        )

        return AmneziaWGRuntimePlan(
            interface=interface,
            runtime_path=runtime_path,
            runtime_config=runtime_config,
            upload_command=upload_command,
            sync_command=sync_command,
        )

    def apply(
        self,
        config: AmneziaWGConfig,
        interface: str = "WireGuard",
        runtime_path: str = "/tmp/maxvpn-awg-runtime.conf",
    ) -> AmneziaWGRuntimeApplyResult:
        if self._command_executor is None:
            raise RuntimeError("RemoteCommandExecutor is required for apply()")

        plan = self.plan(
            config=config,
            interface=interface,
            runtime_path=runtime_path,
        )

        upload_result = self._command_executor.run(
            list(plan.upload_command),
            stdin=plan.runtime_config,
        )

        if upload_result.returncode != 0:
            return AmneziaWGRuntimeApplyResult(
                plan=plan,
                upload_returncode=upload_result.returncode,
                sync_returncode=None,
                uploaded=False,
                applied=False,
                reason=(
                    "runtime_config_upload_failed: "
                    + (upload_result.stderr or upload_result.stdout or "unknown error")
                ),
            )

        sync_result = self._command_executor.run(list(plan.sync_command))

        if sync_result.returncode != 0:
            return AmneziaWGRuntimeApplyResult(
                plan=plan,
                upload_returncode=upload_result.returncode,
                sync_returncode=sync_result.returncode,
                uploaded=True,
                applied=False,
                reason=(
                    "awg_syncconf_failed: "
                    + (sync_result.stderr or sync_result.stdout or "unknown error")
                ),
            )

        return AmneziaWGRuntimeApplyResult(
            plan=plan,
            upload_returncode=upload_result.returncode,
            sync_returncode=sync_result.returncode,
            uploaded=True,
            applied=True,
            reason=None,
        )
