from __future__ import annotations

from backend.models.amneziawg_runtime_snapshot import (
    AmneziaWGRuntimeSnapshot,
)
from backend.ports.amneziawg_runtime_snapshot import (
    AmneziaWGRuntimeSnapshotPort,
)
from backend.ports.remote_command_executor import RemoteCommandExecutor


class SSHAmneziaWGRuntimeSnapshot(
    AmneziaWGRuntimeSnapshotPort,
):
    def __init__(
        self,
        executor: RemoteCommandExecutor,
        runtime_path: str = "/tmp/maxvpn-awg-rollback.conf",
    ) -> None:
        if not runtime_path:
            raise ValueError("runtime_path must not be empty")

        self._executor = executor
        self._runtime_path = runtime_path

    def capture(
        self,
        interface: str,
    ) -> AmneziaWGRuntimeSnapshot:
        if not interface:
            raise ValueError("interface must not be empty")

        result = self._executor.run(
            [
                "awg",
                "showconf",
                interface,
            ],
        )

        if result.returncode != 0:
            raise RuntimeError("awg_showconf_failed")

        if not result.stdout.strip():
            raise RuntimeError("awg_showconf_empty")

        return AmneziaWGRuntimeSnapshot(
            interface=interface,
            config_text=result.stdout,
        )

    def restore(
        self,
        snapshot: AmneziaWGRuntimeSnapshot,
    ) -> None:
        if not snapshot.config_text.strip():
            raise ValueError("snapshot config must not be empty")

        upload_result = self._executor.run(
            [
                "sh",
                "-c",
                (f"cat > {self._runtime_path} && chmod 600 {self._runtime_path}"),
            ],
            stdin=snapshot.config_text,
        )

        if upload_result.returncode != 0:
            raise RuntimeError("rollback_config_upload_failed")

        sync_result = self._executor.run(
            [
                "awg",
                "syncconf",
                snapshot.interface,
                self._runtime_path,
            ],
        )

        if sync_result.returncode != 0:
            raise RuntimeError("rollback_syncconf_failed")
