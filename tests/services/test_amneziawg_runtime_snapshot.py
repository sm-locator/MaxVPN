from unittest.mock import Mock

import pytest

from backend.infrastructure.wireguard.ssh_amneziawg_runtime_snapshot import (
    SSHAmneziaWGRuntimeSnapshot,
)
from backend.models.command_result import CommandResult


def make_executor() -> Mock:
    return Mock()


def test_capture_reads_awg_showconf() -> None:
    executor = make_executor()
    executor.run.return_value = CommandResult(
        returncode=0,
        stdout="[Interface]\nPrivateKey = secret\n",
        stderr="",
    )

    service = SSHAmneziaWGRuntimeSnapshot(executor)

    snapshot = service.capture("WireGuard")

    assert snapshot.interface == "WireGuard"
    assert snapshot.config_text == ("[Interface]\nPrivateKey = secret\n")

    executor.run.assert_called_once_with(
        ["awg", "showconf", "WireGuard"],
    )


def test_capture_rejects_command_failure() -> None:
    executor = make_executor()
    executor.run.return_value = CommandResult(
        returncode=1,
        stdout="",
        stderr="failed",
    )

    service = SSHAmneziaWGRuntimeSnapshot(executor)

    with pytest.raises(
        RuntimeError,
        match="awg_showconf_failed",
    ):
        service.capture("WireGuard")


def test_capture_rejects_empty_config() -> None:
    executor = make_executor()
    executor.run.return_value = CommandResult(
        returncode=0,
        stdout="",
        stderr="",
    )

    service = SSHAmneziaWGRuntimeSnapshot(executor)

    with pytest.raises(
        RuntimeError,
        match="awg_showconf_empty",
    ):
        service.capture("WireGuard")


def test_restore_uploads_and_syncs_snapshot() -> None:
    executor = make_executor()
    executor.run.side_effect = [
        CommandResult(
            returncode=0,
            stdout="[Interface]\\nPrivateKey = old-secret\\n",
            stderr="",
        ),
        CommandResult(
            returncode=0,
            stdout="",
            stderr="",
        ),
        CommandResult(
            returncode=0,
            stdout="",
            stderr="",
        ),
    ]

    service = SSHAmneziaWGRuntimeSnapshot(executor)

    snapshot = service.capture("WireGuard")

    # Replace the capture result with a deterministic snapshot
    # while retaining the real restore contract.
    restored = type(snapshot)(
        interface="WireGuard",
        config_text="[Interface]\nPrivateKey = secret\n",
    )

    service.restore(restored)

    assert executor.run.call_count == 3

    commands = [call.args[0] for call in executor.run.call_args_list]

    assert commands[0] == [
        "awg",
        "showconf",
        "WireGuard",
    ]

    assert commands[2] == [
        "awg",
        "syncconf",
        "WireGuard",
        "/tmp/maxvpn-awg-rollback.conf",
    ]


def test_restore_requires_non_empty_snapshot() -> None:
    executor = make_executor()
    service = SSHAmneziaWGRuntimeSnapshot(executor)

    snapshot = type(
        "Snapshot",
        (),
        {
            "interface": "WireGuard",
            "config_text": "",
        },
    )()

    with pytest.raises(
        ValueError,
        match="snapshot config must not be empty",
    ):
        service.restore(snapshot)
