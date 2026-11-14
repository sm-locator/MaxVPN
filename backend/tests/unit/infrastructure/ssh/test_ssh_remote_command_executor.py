from unittest.mock import Mock, patch

from backend.infrastructure.ssh.ssh_remote_command_executor import (
    SSHRemoteCommandExecutor,
)


def test_ssh_executor_passes_timeout_to_subprocess():
    executor = SSHRemoteCommandExecutor(
        host="192.168.8.1",
        username="root",
        private_key_path="/tmp/key",
        timeout=5.0,
    )

    completed = Mock()
    completed.stdout = "ok"
    completed.stderr = ""
    completed.returncode = 0

    with patch(
        "backend.infrastructure.ssh.ssh_remote_command_executor.subprocess.run",
        return_value=completed,
    ) as run:
        result = executor.run(["echo", "ok"])

    assert result.returncode == 0
    assert result.stdout == "ok"

    assert run.call_args.kwargs["timeout"] == 5.0


def test_ssh_executor_returns_timeout_code_on_expiration():
    executor = SSHRemoteCommandExecutor(
        host="192.168.8.1",
        username="root",
        private_key_path="/tmp/key",
        timeout=5.0,
    )

    import subprocess

    with patch(
        "backend.infrastructure.ssh.ssh_remote_command_executor.subprocess.run",
        side_effect=subprocess.TimeoutExpired(
            cmd=["ssh"],
            timeout=5.0,
        ),
    ):
        result = executor.run(["sleep", "10"])

    assert result.returncode == 124
    assert "timed out" in result.stderr
