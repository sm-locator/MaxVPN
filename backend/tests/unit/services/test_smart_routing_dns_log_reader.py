from unittest.mock import Mock

from backend.ports.remote_command_executor import RemoteCommandExecutor
from backend.services.smart_routing_dns_log_reader import (
    SmartRoutingDnsLogCursor,
    SmartRoutingDnsLogReader,
)


def make_executor(*results) -> Mock:
    executor = Mock(spec=RemoteCommandExecutor)
    executor.run.side_effect = list(results)
    return executor


def result(stdout: str, returncode: int = 0, stderr: str = ""):
    return Mock(
        stdout=stdout,
        returncode=returncode,
        stderr=stderr,
    )


def test_first_read_starts_from_zero() -> None:
    executor = make_executor(
        result("12345 78\n"),
        result(
            "Sep 12 00:00:01 dnsmasq[100]: "
            "1 127.0.0.1/12345 query[A] example.com from 127.0.0.1\n"
        ),
    )

    service = SmartRoutingDnsLogReader(executor)

    observed = service.read()

    assert observed.lines == (
        "Sep 12 00:00:01 dnsmasq[100]: "
        "1 127.0.0.1/12345 query[A] example.com from 127.0.0.1",
    )
    assert observed.cursor.inode == 12345
    assert observed.reset is False

    dd_command = executor.run.call_args_list[1].args[0]
    assert "bs=4096 skip=0" in dd_command[2]


def test_second_read_uses_existing_offset() -> None:
    executor = make_executor(
        result("12345 109\n"),
        result("new line\n"),
    )

    service = SmartRoutingDnsLogReader(executor)

    observed = service.read(
        SmartRoutingDnsLogCursor(
            inode=12345,
            offset=100,
        )
    )

    assert observed.lines == ("new line",)
    assert observed.cursor == SmartRoutingDnsLogCursor(
        inode=12345,
        offset=109,
    )
    assert observed.reset is False

    dd_command = executor.run.call_args_list[1].args[0]
    assert "bs=4096 skip=0" in dd_command[2]
    assert "tail -c +101" in dd_command[2]


def test_same_size_returns_no_lines() -> None:
    executor = make_executor(
        result("12345 100\n"),
    )

    service = SmartRoutingDnsLogReader(executor)

    observed = service.read(
        SmartRoutingDnsLogCursor(
            inode=12345,
            offset=100,
        )
    )

    assert observed.lines == ()
    assert observed.cursor == SmartRoutingDnsLogCursor(
        inode=12345,
        offset=100,
    )
    assert observed.reset is False
    assert executor.run.call_count == 1


def test_inode_change_resets_offset() -> None:
    executor = make_executor(
        result("98765 11\n"),
        result("fresh line\n"),
    )

    service = SmartRoutingDnsLogReader(executor)

    observed = service.read(
        SmartRoutingDnsLogCursor(
            inode=12345,
            offset=900,
        )
    )

    assert observed.lines == ("fresh line",)
    assert observed.cursor.inode == 98765
    assert observed.cursor.offset == len("fresh line\n".encode())
    assert observed.reset is True

    dd_command = executor.run.call_args_list[1].args[0]
    assert "bs=4096 skip=0" in dd_command[2]


def test_truncation_resets_offset() -> None:
    executor = make_executor(
        result("12345 20\n"),
        result("after truncate\n"),
    )

    service = SmartRoutingDnsLogReader(executor)

    observed = service.read(
        SmartRoutingDnsLogCursor(
            inode=12345,
            offset=100,
        )
    )

    assert observed.reset is True
    assert observed.lines == ("after truncate",)

    dd_command = executor.run.call_args_list[1].args[0]
    assert "bs=4096 skip=0" in dd_command[2]


def test_missing_log_keeps_cursor() -> None:
    executor = make_executor(
        result(""),
    )

    service = SmartRoutingDnsLogReader(executor)

    cursor = SmartRoutingDnsLogCursor(12345, 100)

    observed = service.read(cursor)

    assert observed.lines == ()
    assert observed.cursor == cursor
    assert observed.reset is False


def test_remote_command_failure_is_reported() -> None:
    executor = make_executor(
        result("", returncode=1, stderr="stat failed"),
    )

    service = SmartRoutingDnsLogReader(executor)

    try:
        service.read()
    except RuntimeError as exc:
        assert "Smart Routing DNS log command failed" in str(exc)
    else:
        raise AssertionError("RuntimeError was not raised")


def test_large_offset_uses_blocked_reading() -> None:
    executor = make_executor(
        result("12345 597239\n"),
        result("new line\n"),
    )

    service = SmartRoutingDnsLogReader(executor)

    observed = service.read(
        SmartRoutingDnsLogCursor(
            inode=12345,
            offset=597230,
        )
    )

    assert observed.lines == ("new line",)
    assert observed.cursor == SmartRoutingDnsLogCursor(
        inode=12345,
        offset=597239,
    )
    assert observed.reset is False

    read_command = executor.run.call_args_list[1].args[0][2]

    assert "bs=4096" in read_command
    assert "skip=145" in read_command
    assert "tail -c +3311" in read_command
    assert "head -c 9" in read_command
    assert "bs=1" not in read_command
