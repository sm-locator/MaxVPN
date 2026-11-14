from unittest.mock import Mock

import pytest
from backend.models.command_result import CommandResult
from backend.services.smart_routing_runtime_state import (
    SmartRoutingRuntimeStateCollector,
)


def result(stdout: str, returncode: int = 0) -> CommandResult:
    return CommandResult(
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


def test_collect_parses_runtime_state() -> None:
    executor = Mock()

    executor.run.side_effect = [
        result("""Name: MAXVPN_DIRECT
Type: hash:ip
Header: family inet
Members:
192.0.2.10
192.0.2.20
"""),
        result("""Name: MAXVPN_DIRECT_STATIC
Type: hash:ip
Header: family inet
Members:
192.0.2.30
"""),
        result("""Name: MAXVPN_DIRECT6
Type: hash:ip
Header: family inet6
Members:
2001:db8::10
2001:db8::20
"""),
        result("""dhcp.@ipset[3]=ipset
dhcp.@ipset[3].name='MAXVPN_DIRECT'
dhcp.@ipset[3].domain='example.com'
dhcp.@ipset[3].domain='example.net'
"""),
        result("""/var/etc/dnsmasq.conf.cfg01411c:36:ipset=/example.com/MAXVPN_DIRECT
/var/etc/dnsmasq.conf.cfg01411c:37:ipset=/example.net/MAXVPN_DIRECT
"""),
        result("""0: from all lookup local
100: from all fwmark 0x64/0xff lookup 200
1000: from all iif br-lan lookup 100
32766: from all lookup main
"""),
        result("""default via 46.48.56.1 dev eth1
192.168.8.0/24 dev br-lan
"""),
    ]

    state = SmartRoutingRuntimeStateCollector(executor).collect()

    assert state.direct_ipv4_addresses == (
        "192.0.2.10",
        "192.0.2.20",
        "192.0.2.30",
    )
    assert state.static_direct_ipv4_addresses == ("192.0.2.30",)
    assert state.direct_ipv6_addresses == (
        "2001:db8::10",
        "2001:db8::20",
    )
    assert state.direct_domains == (
        "example.com",
        "example.net",
    )
    assert state.rendered_domains == (
        "example.com",
        "example.net",
    )
    assert state.routing_table_200 == (
        "default via 46.48.56.1 dev eth1",
        "192.168.8.0/24 dev br-lan",
    )


def test_collect_uses_only_read_only_commands() -> None:
    executor = Mock()

    executor.run.side_effect = [
        result(""),
        result(""),
        result(""),
        result(""),
        result(""),
        result(""),
        result(""),
    ]

    SmartRoutingRuntimeStateCollector(executor).collect()

    commands = [call.args[0] for call in executor.run.call_args_list]

    assert commands == [
        ["ipset", "list", "MAXVPN_DIRECT"],
        ["ipset", "list", "MAXVPN_DIRECT_STATIC"],
        ["ipset", "list", "MAXVPN_DIRECT6"],
        ["uci", "show", "dhcp"],
        [
            "sh",
            "-c",
            "set -- /var/etc/dnsmasq.conf*; "
            "found=0; "
            'for path do [ -f "$path" ] && found=1; done; '
            '[ "$found" -eq 1 ] || { '
            "echo 'smart_routing_dnsmasq_config_missing' >&2; exit 2; }; "
            "grep -Rni 'ipset=/.*\\/MAXVPN_DIRECT$' "
            "/var/etc/dnsmasq.conf* 2>/dev/null || true",
        ],
        ["ip", "rule", "show"],
        ["ip", "route", "show", "table", "200"],
    ]


def test_parse_uci_domains_uses_only_maxvpn_direct_section() -> None:
    output = """dhcp.@ipset[0]=ipset
dhcp.@ipset[0].name='OTHER_SET'
dhcp.@ipset[0].domain='other.example'
dhcp.@ipset[3]=ipset
dhcp.@ipset[3].name='MAXVPN_DIRECT'
dhcp.@ipset[3].domain='example.com'
dhcp.@ipset[3].domain='example.net'
"""

    assert SmartRoutingRuntimeStateCollector._parse_uci_domains(output) == (
        "example.com",
        "example.net",
    )


def test_parse_uci_domains_handles_multiple_values_in_one_list_line() -> None:
    output = """dhcp.@ipset[3]=ipset
dhcp.@ipset[3].name='MAXVPN_DIRECT'
dhcp.@ipset[3].domain='2gis.ru' 'alfabank.ru' 'avito.ru'
"""

    assert SmartRoutingRuntimeStateCollector._parse_uci_domains(output) == (
        "2gis.ru",
        "alfabank.ru",
        "avito.ru",
    )


def test_parse_rendered_domains_handles_multiple_domains_in_one_ipset_line() -> None:
    output = (
        "/var/etc/dnsmasq.conf.cfg01411c:36:"
        "ipset=/2gis.ru/alfabank.ru/avito.ru/MAXVPN_DIRECT\n"
        "/var/etc/dnsmasq.conf.cfg01411c:37:"
        "ipset=/static.example/MAXVPN_DIRECT_STATIC\n"
    )

    assert SmartRoutingRuntimeStateCollector._parse_rendered_domains(output) == (
        "2gis.ru",
        "alfabank.ru",
        "avito.ru",
    )


def test_parse_ipset_parses_only_ipv6_members_for_family_6() -> None:
    output = """Name: MAXVPN_DIRECT6
Type: hash:ip
Header: family inet6
Members:
2001:db8::20
192.0.2.10
2001:db8::10
"""

    assert SmartRoutingRuntimeStateCollector._parse_ipset(
        output,
        family=6,
    ) == (
        "2001:db8::10",
        "2001:db8::20",
    )


def test_parse_ipset_parses_only_ipv4_members_for_family_4() -> None:
    output = """Name: MAXVPN_DIRECT
Type: hash:ip
Header: family inet
Members:
2001:db8::20
192.0.2.20
192.0.2.10
"""

    assert SmartRoutingRuntimeStateCollector._parse_ipset(
        output,
        family=4,
    ) == (
        "192.0.2.10",
        "192.0.2.20",
    )


def test_collect_handles_missing_ipv6_ipset() -> None:
    executor = Mock()

    executor.run.side_effect = [
        result(""),
        result(""),
        result("", returncode=1),
        result(""),
        result(""),
        result(""),
        result(""),
    ]

    state = SmartRoutingRuntimeStateCollector(executor).collect()

    assert state.direct_ipv6_addresses == ()


def test_collect_fails_closed_when_uci_dns_policy_cannot_be_read() -> None:
    executor = Mock()
    executor.run.side_effect = [
        result(""),
        result(""),
        result("", returncode=1),  # The IPv6 set may be absent.
        result("", returncode=2),  # UCI read failure must not mean no domains.
        result(""),
        result(""),
        result(""),
    ]

    with pytest.raises(
        RuntimeError,
        match="smart_routing_runtime_state_read_failed: source=uci show dhcp",
    ):
        SmartRoutingRuntimeStateCollector(executor).collect()


def test_collect_fails_closed_when_dnsmasq_config_is_unavailable() -> None:
    executor = Mock()
    executor.run.side_effect = [
        result(""),
        result(""),
        result("", returncode=1),  # The IPv6 set may be absent.
        result(""),
        result("", returncode=2),  # No rendered config cannot prove empty state.
        result(""),
        result(""),
    ]

    with pytest.raises(
        RuntimeError,
        match="smart_routing_runtime_state_read_failed: source=rendered dnsmasq config",
    ):
        SmartRoutingRuntimeStateCollector(executor).collect()
