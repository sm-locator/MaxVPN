from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from backend.models.command_result import CommandResult
from backend.ports.remote_command_executor import RemoteCommandExecutor


class SSHRemoteCommandExecutor(RemoteCommandExecutor):
    """
    Executes commands on a remote host through the system ssh client.
    """

    def __init__(
        self,
        host: str,
        username: str,
        private_key_path: str,
        port: int = 22,
        ssh_binary: str = "ssh",
        timeout: float | None = None,
    ) -> None:
        self._host = host
        self._username = username
        self._private_key_path = str(Path(private_key_path).expanduser())
        self._port = port
        self._ssh_binary = ssh_binary
        self._timeout = timeout
        control_dir = self._private_control_directory()
        key_hash = hashlib.sha256(self._private_key_path.encode("utf-8")).hexdigest()[
            :10
        ]
        self._control_path = (
            str(control_dir / f"{key_hash}-%C") if control_dir is not None else None
        )

    @staticmethod
    def _private_control_directory() -> Path | None:
        """Create a private local directory for OpenSSH control sockets."""
        try:
            uid = os.getuid()
            directory = Path(tempfile.gettempdir()) / f"maxvpn-ssh-{uid}"
            if directory.is_symlink():
                return None
            directory.mkdir(mode=0o700, exist_ok=True)
            if directory.is_symlink() or not directory.is_dir():
                return None
            if directory.stat().st_uid != uid:
                return None
            directory.chmod(0o700)
            return directory
        except OSError:
            # If a private control directory is unavailable, SSH continues
            # without multiplexing rather than breaking remote commands.
            return None

    def run(
        self,
        command: list[str],
        stdin: str | None = None,
    ) -> CommandResult:
        if not command:
            raise ValueError("Remote command must not be empty.")

        ssh_command = [
            self._ssh_binary,
            "-i",
            self._private_key_path,
            "-p",
            str(self._port),
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
        ]
        if self._control_path is not None:
            ssh_command.extend(
                [
                    "-o",
                    "ControlMaster=auto",
                    "-o",
                    "ControlPersist=30s",
                    "-o",
                    f"ControlPath={self._control_path}",
                ]
            )
        ssh_command.extend(
            [
                f"{self._username}@{self._host}",
                shlex.join(command),
            ]
        )

        try:
            result = subprocess.run(
                ssh_command,
                input=stdin,
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                stdout=(exc.stdout or ""),
                stderr=(
                    (exc.stderr or "")
                    or f"SSH command timed out after {self._timeout} seconds"
                ),
                returncode=124,
            )

        return CommandResult(
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
            returncode=result.returncode,
        )
