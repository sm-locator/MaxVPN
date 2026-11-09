from unittest.mock import Mock, call

from backend.infrastructure.openwrt.openwrt_smart_routing_dns_cleanup import (
    OpenWrtSmartRoutingDnsCleanup,
)
from backend.models.command_result import CommandResult


def result(returncode: int = 0, stderr: str = "") -> CommandResult:
    return CommandResult(
        returncode=returncode,
        stdout="",
        stderr=stderr,
    )


def test_add_addresses_adds_only_to_dns_ipset() -> None:
    executor = Mock()
    executor.run.return_value = result()

    service = OpenWrtSmartRoutingDnsCleanup(executor)

    added = service.add_addresses(
        (
            "81.90.181.120",
            "81.90.181.115",
        ),
    )

    assert added == (
        "81.90.181.120",
        "81.90.181.115",
    )

    assert executor.run.call_args_list == [
        call(
            [
                "ipset",
                "add",
                "MAXVPN_DIRECT",
                "81.90.181.120",
                "-exist",
            ]
        ),
        call(
            [
                "ipset",
                "add",
                "MAXVPN_DIRECT",
                "81.90.181.115",
                "-exist",
            ]
        ),
    ]


def test_add_addresses_rejects_invalid_ip() -> None:
    executor = Mock()
    service = OpenWrtSmartRoutingDnsCleanup(executor)

    try:
        service.add_addresses(("not-an-ip",))
    except ValueError:
        pass
    else:
        raise AssertionError("ValueError was expected")

    executor.run.assert_not_called()


def test_add_addresses_raises_on_command_failure() -> None:
    executor = Mock()
    executor.run.return_value = result(
        returncode=2,
        stderr="failed",
    )

    service = OpenWrtSmartRoutingDnsCleanup(executor)

    try:
        service.add_addresses(("81.90.181.120",))
    except RuntimeError as exc:
        assert "smart_routing_dns_add_failed" in str(exc)
    else:
        raise AssertionError("RuntimeError was expected")


def test_remove_stale_deletes_only_direct_dns_ips() -> None:
    executor = Mock()
    executor.run.return_value = result()

    service = OpenWrtSmartRoutingDnsCleanup(executor)

    removed = service.remove_stale(
        (
            "81.90.181.103",
            "81.90.181.115",
        ),
    )

    assert removed == (
        "81.90.181.103",
        "81.90.181.115",
    )

    assert executor.run.call_args_list == [
        call(["ipset", "del", "MAXVPN_DIRECT", "81.90.181.103"]),
        call(["ipset", "del", "MAXVPN_DIRECT", "81.90.181.115"]),
    ]


def test_remove_stale_does_not_fail_when_ip_is_already_missing() -> None:
    executor = Mock()
    executor.run.return_value = result(returncode=1)

    service = OpenWrtSmartRoutingDnsCleanup(executor)

    removed = service.remove_stale(("81.90.181.103",))

    assert removed == ()
    executor.run.assert_called_once_with(
        ["ipset", "del", "MAXVPN_DIRECT", "81.90.181.103"],
    )


def test_remove_stale_rejects_invalid_ip() -> None:
    executor = Mock()
    service = OpenWrtSmartRoutingDnsCleanup(executor)

    try:
        service.remove_stale(("not-an-ip",))
    except ValueError:
        pass
    else:
        raise AssertionError("ValueError was expected")

    executor.run.assert_not_called()


def test_remove_stale_raises_on_unexpected_command_failure() -> None:
    executor = Mock()
    executor.run.return_value = result(
        returncode=2,
        stderr="permission denied",
    )

    service = OpenWrtSmartRoutingDnsCleanup(executor)

    try:
        service.remove_stale(("81.90.181.103",))
    except RuntimeError as exc:
        assert "smart_routing_dns_cleanup_failed" in str(exc)
    else:
        raise AssertionError("RuntimeError was expected")


def test_add_ipv6_addresses_adds_only_to_ipv6_dns_ipset() -> None:
    executor = Mock()
    executor.run.return_value = result()

    service = OpenWrtSmartRoutingDnsCleanup(executor)

    added = service.add_ipv6_addresses(
        (
            "2001:db8::20",
            "2001:db8::10",
        ),
    )

    assert added == (
        "2001:db8::20",
        "2001:db8::10",
    )

    assert executor.run.call_args_list == [
        call(
            [
                "ipset",
                "add",
                "MAXVPN_DIRECT6",
                "2001:db8::20",
                "-exist",
            ]
        ),
        call(
            [
                "ipset",
                "add",
                "MAXVPN_DIRECT6",
                "2001:db8::10",
                "-exist",
            ]
        ),
    ]


def test_add_ipv6_addresses_rejects_invalid_ipv6() -> None:
    executor = Mock()
    service = OpenWrtSmartRoutingDnsCleanup(executor)

    try:
        service.add_ipv6_addresses(("not-an-ipv6",))
    except ValueError:
        pass
    else:
        raise AssertionError("ValueError was expected")

    executor.run.assert_not_called()


def test_add_ipv6_addresses_rejects_ipv4() -> None:
    executor = Mock()
    service = OpenWrtSmartRoutingDnsCleanup(executor)

    try:
        service.add_ipv6_addresses(("192.0.2.10",))
    except ValueError:
        pass
    else:
        raise AssertionError("ValueError was expected")

    executor.run.assert_not_called()


def test_add_ipv6_addresses_raises_on_command_failure() -> None:
    executor = Mock()
    executor.run.return_value = result(
        returncode=2,
        stderr="failed",
    )

    service = OpenWrtSmartRoutingDnsCleanup(executor)

    try:
        service.add_ipv6_addresses(("2001:db8::10",))
    except RuntimeError as exc:
        assert "smart_routing_dns_add_ipv6_failed" in str(exc)
    else:
        raise AssertionError("RuntimeError was expected")


def test_remove_stale_ipv6_deletes_only_ipv6_dns_ips() -> None:
    executor = Mock()
    executor.run.return_value = result()

    service = OpenWrtSmartRoutingDnsCleanup(executor)

    removed = service.remove_stale_ipv6(
        (
            "2001:db8::10",
            "2001:db8::20",
        ),
    )

    assert removed == (
        "2001:db8::10",
        "2001:db8::20",
    )

    assert executor.run.call_args_list == [
        call(
            [
                "ipset",
                "del",
                "MAXVPN_DIRECT6",
                "2001:db8::10",
            ]
        ),
        call(
            [
                "ipset",
                "del",
                "MAXVPN_DIRECT6",
                "2001:db8::20",
            ]
        ),
    ]


def test_remove_stale_ipv6_ignores_already_missing_address() -> None:
    executor = Mock()
    executor.run.return_value = result(returncode=1)

    service = OpenWrtSmartRoutingDnsCleanup(executor)

    removed = service.remove_stale_ipv6(("2001:db8::10",))

    assert removed == ()
    executor.run.assert_called_once_with(
        [
            "ipset",
            "del",
            "MAXVPN_DIRECT6",
            "2001:db8::10",
        ]
    )


def test_remove_stale_ipv6_rejects_invalid_ipv6() -> None:
    executor = Mock()
    service = OpenWrtSmartRoutingDnsCleanup(executor)

    try:
        service.remove_stale_ipv6(("not-an-ipv6",))
    except ValueError:
        pass
    else:
        raise AssertionError("ValueError was expected")

    executor.run.assert_not_called()


def test_remove_stale_ipv6_raises_on_unexpected_command_failure() -> None:
    executor = Mock()
    executor.run.return_value = result(
        returncode=2,
        stderr="permission denied",
    )

    service = OpenWrtSmartRoutingDnsCleanup(executor)

    try:
        service.remove_stale_ipv6(("2001:db8::10",))
    except RuntimeError as exc:
        assert "smart_routing_dns_cleanup_ipv6_failed" in str(exc)
    else:
        raise AssertionError("RuntimeError was expected")


def test_ipv6_cleanup_never_writes_to_ipv4_ipset() -> None:
    executor = Mock()
    executor.run.return_value = result()

    service = OpenWrtSmartRoutingDnsCleanup(executor)

    service.add_ipv6_addresses(("2001:db8::10",))
    service.remove_stale_ipv6(("2001:db8::10",))

    commands = [item.args[0] for item in executor.run.call_args_list]

    assert all(command[2] == "MAXVPN_DIRECT6" for command in commands)


def test_ipv4_cleanup_never_writes_to_ipv6_ipset() -> None:
    executor = Mock()
    executor.run.return_value = result()

    service = OpenWrtSmartRoutingDnsCleanup(executor)

    service.add_addresses(("192.0.2.10",))
    service.remove_stale(("192.0.2.10",))

    commands = [item.args[0] for item in executor.run.call_args_list]

    assert all(command[2] == "MAXVPN_DIRECT" for command in commands)
