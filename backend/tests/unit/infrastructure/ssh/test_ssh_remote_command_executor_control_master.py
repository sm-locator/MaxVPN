from __future__ import annotations

import subprocess

from backend.infrastructure.ssh import (
    ssh_remote_command_executor as ssh_module,
)


def test_executor_configures_secure_ssh_multiplexing(monkeypatch, tmp_path) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="vless\n",
            stderr="",
        )

    monkeypatch.setattr(ssh_module.subprocess, "run", fake_run)

    key_path = tmp_path / "test_key"
    executor = ssh_module.SSHRemoteCommandExecutor(
        host="192.168.8.1",
        username="root",
        private_key_path=str(key_path),
    )

    result = executor.run(["cat", "/tmp/runtime-mode"])

    assert result.returncode == 0
    assert result.stdout == "vless"

    args = calls[0][0]
    assert "ConnectTimeout=5" in args
    assert "ControlMaster=auto" in args
    assert "ControlPersist=30s" in args
    assert any(
        item.startswith("ControlPath=") and item.endswith("-%C") for item in args
    )

    # Same destination and key path should reuse the same local socket.
    second = ssh_module.SSHRemoteCommandExecutor(
        host="192.168.8.1",
        username="root",
        private_key_path=str(key_path),
    )
    assert second._control_path == executor._control_path
