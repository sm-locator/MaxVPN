from datetime import datetime, timezone
from unittest.mock import Mock

from backend.infrastructure.wireguard.ssh_amneziawg_health_checker import (
    SSHAmneziaWGHealthChecker,
)
from backend.models.command_result import CommandResult
from backend.models.wireguard_health import WireGuardHealthStatus
from backend.ports.remote_command_executor import RemoteCommandExecutor

INTERFACE_UP_OUTPUT = (
    "17: WireGuard: <POINTOPOINT,NOARP,UP,LOWER_UP> "
    "mtu 1380 qdisc noqueue state UNKNOWN\n"
    "    link/none\n"
)

AWG_DUMP = (
    "oBGphdOhJXLWTd/qgAcXkiEPVZio/mfa6rr66YV9V3E= "
    "pBGNU9zr9xfiXae6IUYPaVihQ6KQyU/4HkjMqZc20SA= "
    "45121 5 2 90 0 0 0 1 2 3 4 "
    "(null) (null) (null) (null) (null) off\n"
    "GUdxiwBvCKYlZL7NjGfek1vES+JuTl1pogI2CWxNoVo= "
    "2DlNQOBs5a73uOu4QM2hHHoYW3xNUyuOCEax48If0/g= "
    "45.141.215.26:51820 0.0.0.0/0,::/0 "
    "1786815590 44439924232 2968086115 25\n"
)


def test_check_reads_remote_amneziawg_state() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        CommandResult(
            stdout=INTERFACE_UP_OUTPUT,
            stderr="",
            returncode=0,
        ),
        CommandResult(
            stdout=AWG_DUMP,
            stderr="",
            returncode=0,
        ),
    ]

    checker = SSHAmneziaWGHealthChecker(
        executor=executor,
        interface_name="WireGuard",
    )

    health = checker.check()

    assert health.interface_exists is True
    assert health.interface_up is True
    assert health.listen_port == 45121
    assert health.peer_count == 1
    assert health.latest_handshake == datetime.fromtimestamp(
        1786815590,
        tz=timezone.utc,
    )
    assert health.rx_bytes == 44439924232
    assert health.tx_bytes == 2968086115
    assert health.status is WireGuardHealthStatus.UNKNOWN
    assert health.reason is None

    assert executor.run.call_count == 2
    executor.run.assert_any_call(
        [
            "ip",
            "link",
            "show",
            "dev",
            "WireGuard",
        ]
    )
    executor.run.assert_any_call(
        [
            "awg",
            "show",
            "WireGuard",
            "dump",
        ]
    )


def test_check_reports_remote_interface_failure() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.return_value = CommandResult(
        stdout="",
        stderr="Device not found",
        returncode=1,
    )

    checker = SSHAmneziaWGHealthChecker(
        executor=executor,
        interface_name="WireGuard",
    )

    health = checker.check()

    assert health.interface_exists is False
    assert health.interface_up is False
    assert health.status is WireGuardHealthStatus.FAILED
    assert health.reason == "interface_not_found"

    executor.run.assert_called_once_with(
        [
            "ip",
            "link",
            "show",
            "dev",
            "WireGuard",
        ]
    )


def test_check_reports_remote_awg_failure() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        CommandResult(
            stdout=INTERFACE_UP_OUTPUT,
            stderr="",
            returncode=0,
        ),
        CommandResult(
            stdout="",
            stderr="interface not found",
            returncode=1,
        ),
    ]

    checker = SSHAmneziaWGHealthChecker(
        executor=executor,
        interface_name="WireGuard",
    )

    health = checker.check()

    assert health.interface_exists is True
    assert health.interface_up is True
    assert health.status is WireGuardHealthStatus.FAILED
    assert health.reason == "awg_dump_failed"


def test_check_reports_invalid_remote_dump() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        CommandResult(
            stdout=INTERFACE_UP_OUTPUT,
            stderr="",
            returncode=0,
        ),
        CommandResult(
            stdout="broken dump",
            stderr="",
            returncode=0,
        ),
    ]

    checker = SSHAmneziaWGHealthChecker(
        executor=executor,
        interface_name="WireGuard",
    )

    health = checker.check()

    assert health.interface_exists is True
    assert health.interface_up is True
    assert health.status is WireGuardHealthStatus.FAILED
    assert health.reason == "invalid_awg_dump"
