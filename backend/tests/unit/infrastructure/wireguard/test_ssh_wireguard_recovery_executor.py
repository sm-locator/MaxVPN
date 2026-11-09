from unittest.mock import Mock, call

import pytest
from backend.infrastructure.wireguard.ssh_wireguard_recovery_executor import (
    SSHWireGuardRecoveryExecutor,
)
from backend.models.command_result import CommandResult
from backend.models.wireguard_recovery import (
    WireGuardRecoveryAction,
    WireGuardRecoveryPlan,
)
from backend.ports.remote_command_executor import RemoteCommandExecutor


def make_plan(
    action: WireGuardRecoveryAction,
    attempt: int = 1,
) -> WireGuardRecoveryPlan:
    return WireGuardRecoveryPlan(
        action=action,
        attempt=attempt,
        max_attempts=3,
        backoff_seconds=5,
        reason="handshake_timeout",
    )


def test_build_restart_interface_commands() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    recovery = SSHWireGuardRecoveryExecutor(
        executor=executor,
        interface_name="WireGuard",
    )

    commands = recovery.build_commands(
        make_plan(WireGuardRecoveryAction.RESTART_INTERFACE)
    )

    assert commands == [
        ["ifdown", "WireGuard"],
        ["ifup", "WireGuard"],
    ]

    executor.run.assert_not_called()


def test_build_none_plan_returns_no_commands() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    recovery = SSHWireGuardRecoveryExecutor(
        executor=executor,
        interface_name="WireGuard",
    )

    commands = recovery.build_commands(make_plan(WireGuardRecoveryAction.NONE))

    assert commands == []
    executor.run.assert_not_called()


def test_execute_runs_restart_commands_in_order() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        CommandResult(
            stdout="",
            stderr="",
            returncode=0,
        ),
        CommandResult(
            stdout="",
            stderr="",
            returncode=0,
        ),
    ]

    recovery = SSHWireGuardRecoveryExecutor(
        executor=executor,
        interface_name="WireGuard",
    )

    recovery.execute(make_plan(WireGuardRecoveryAction.RESTART_INTERFACE))

    assert executor.run.call_args_list == [
        call(["ifdown", "WireGuard"]),
        call(["ifup", "WireGuard"]),
    ]


def test_execute_stops_when_ifdown_fails() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.return_value = CommandResult(
        stdout="",
        stderr="interface failure",
        returncode=1,
    )

    recovery = SSHWireGuardRecoveryExecutor(
        executor=executor,
        interface_name="WireGuard",
    )

    with pytest.raises(RuntimeError, match="WireGuard recovery command failed"):
        recovery.execute(make_plan(WireGuardRecoveryAction.RESTART_INTERFACE))

    executor.run.assert_called_once_with(["ifdown", "WireGuard"])


def test_execute_stops_when_ifup_fails() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        CommandResult(
            stdout="",
            stderr="",
            returncode=0,
        ),
        CommandResult(
            stdout="",
            stderr="ifup failed",
            returncode=1,
        ),
    ]

    recovery = SSHWireGuardRecoveryExecutor(
        executor=executor,
        interface_name="WireGuard",
    )

    with pytest.raises(RuntimeError, match="WireGuard recovery command failed"):
        recovery.execute(make_plan(WireGuardRecoveryAction.RESTART_INTERFACE))

    assert executor.run.call_args_list == [
        call(["ifdown", "WireGuard"]),
        call(["ifup", "WireGuard"]),
    ]


def test_execute_none_plan_does_nothing() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    recovery = SSHWireGuardRecoveryExecutor(
        executor=executor,
        interface_name="WireGuard",
    )

    recovery.execute(make_plan(WireGuardRecoveryAction.NONE))

    executor.run.assert_not_called()
