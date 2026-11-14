from unittest.mock import Mock

import pytest
from backend.services.smart_routing_domain_diagnostic import (
    SmartRoutingDomainDiagnosticService,
)

DOMAIN = "cian.ru"
IP = "51.250.123.126"
DNS_OUTPUT = (
    f"Server: 127.0.0.1\nAddress: 127.0.0.1#53\n\nName: {DOMAIN}\nAddress: {IP}\n"
)
IPSET_OUTPUT = f"Name: MAXVPN_DIRECT\nType: hash:ip\nMembers:\n{IP}\n198.51.100.10\n"
ROUTE_OUTPUT = f"{IP} via 46.48.56.1 dev eth1 table 200 src 46.48.56.64 mark 0x64\n"


def make_executor(
    *,
    dns_returncode=0,
    dns_stdout=DNS_OUTPUT,
    ipset_returncode=0,
    ipset_stdout=IPSET_OUTPUT,
    dnsmasq_mapping=True,
    marking_rule=True,
    policy_rule=True,
    forward_chain=True,
    forward_accept=True,
    nat_chain=True,
    nat_masquerade=True,
    route_returncode=0,
    route_stdout=ROUTE_OUTPUT,
):
    executor = Mock()

    def run(command):
        command = tuple(command)
        if command[:1] == ("nslookup",):
            return Mock(
                returncode=dns_returncode,
                stdout=dns_stdout,
                stderr="NXDOMAIN" if dns_returncode else "",
            )
        if command == ("ipset", "list", "MAXVPN_DIRECT"):
            return Mock(
                returncode=ipset_returncode,
                stdout=ipset_stdout,
                stderr="ipset unavailable" if ipset_returncode else "",
            )
        if command == ("grep", "-R", "-F", "MAXVPN_DIRECT", "/var/etc"):
            output = (
                f"/var/etc/dnsmasq.conf.cfg01411c:ipset=/{DOMAIN}/MAXVPN_DIRECT\n"
                if dnsmasq_mapping
                else ""
            )
            return Mock(
                returncode=0 if dnsmasq_mapping else 1,
                stdout=output,
                stderr="",
            )
        if command == ("ip", "-4", "rule", "show"):
            output = (
                (
                    "0: from all lookup local\n"
                    "100: from all fwmark 0x64/0xff lookup 200\n"
                )
                if policy_rule
                else "0: from all lookup local\n"
            )
            return Mock(returncode=0, stdout=output, stderr="")

        command_flags = {
            (
                "iptables",
                "-t",
                "mangle",
                "-C",
                "PREROUTING",
                "-i",
                "br-lan",
                "-m",
                "set",
                "--match-set",
                "MAXVPN_DIRECT",
                "dst",
                "-j",
                "MARK",
                "--set-xmark",
                "0x64/0xff",
            ): marking_rule,
            (
                "iptables",
                "-C",
                "forwarding_rule",
                "-j",
                "MAXVPN_LAN_FORWARD",
            ): forward_chain,
            (
                "iptables",
                "-C",
                "MAXVPN_LAN_FORWARD",
                "-i",
                "br-lan",
                "-o",
                "eth1",
                "-m",
                "mark",
                "--mark",
                "0x64/0xff",
                "-j",
                "ACCEPT",
            ): forward_accept,
            (
                "iptables",
                "-t",
                "nat",
                "-C",
                "POSTROUTING",
                "-j",
                "MAXVPN_DIRECT_NAT",
            ): nat_chain,
            (
                "iptables",
                "-t",
                "nat",
                "-C",
                "MAXVPN_DIRECT_NAT",
                "-o",
                "eth1",
                "-m",
                "mark",
                "--mark",
                "0x64/0xff",
                "-j",
                "MASQUERADE",
            ): nat_masquerade,
        }
        if command in command_flags:
            return Mock(
                returncode=0 if command_flags[command] else 1,
                stdout="",
                stderr="",
            )
        if command[:4] == ("ip", "-4", "route", "get"):
            return Mock(
                returncode=route_returncode,
                stdout=route_stdout,
                stderr="route lookup failed" if route_returncode else "",
            )
        raise AssertionError(f"Unexpected diagnostic command: {command!r}")

    executor.run.side_effect = run
    return executor


def test_check_passes_when_full_direct_path_is_healthy():
    result = SmartRoutingDomainDiagnosticService(make_executor()).check("CIAN.RU.")

    assert result.healthy is True
    assert result.domain == "cian.ru"
    assert result.dns_ipv4_addresses == (IP,)
    assert result.present_ipv4_addresses == (IP,)
    assert result.missing_ipv4_addresses == ()
    assert result.direct_ipset_readable is True
    assert result.dnsmasq_mapping_present is True
    assert result.marking_rule_present is True
    assert result.policy_rule_present is True
    assert result.forward_chain_attached is True
    assert result.direct_forward_rule_present is True
    assert result.nat_chain_attached is True
    assert result.nat_masquerade_rule_present is True
    assert result.route_results[0].endswith(" OK")
    assert result.reason is None


def test_check_reports_missing_dnsmasq_mapping_even_if_shared_ip_is_in_ipset():
    result = SmartRoutingDomainDiagnosticService(
        make_executor(dnsmasq_mapping=False)
    ).check(DOMAIN)

    assert result.healthy is False
    assert result.present_ipv4_addresses == (IP,)
    assert result.dnsmasq_mapping_present is False
    assert result.reason == "dnsmasq_direct_mapping_missing"


def test_check_parses_busybox_nslookup_address_number_format():
    busybox_output = chr(10).join(
        (
            "Server: 127.0.0.1",
            "Address: 127.0.0.1#53",
            "",
            "Name: cian.ru",
            "Address 1: 51.250.123.126",
            "*** Can't find cian.ru: No answer",
        )
    )
    result = SmartRoutingDomainDiagnosticService(
        make_executor(dns_stdout=busybox_output)
    ).check(DOMAIN)

    assert result.dns_ipv4_addresses == (IP,)
    assert result.present_ipv4_addresses == (IP,)
    assert result.missing_ipv4_addresses == ()
    assert result.healthy is True
    assert result.reason is None


def test_check_reports_dns_ip_missing_from_direct_ipset():
    ipset_output = "Name: MAXVPN_DIRECT\nType: hash:ip\nMembers:\n198.51.100.10\n"
    result = SmartRoutingDomainDiagnosticService(
        make_executor(ipset_stdout=ipset_output)
    ).check(DOMAIN)

    assert result.healthy is False
    assert result.dns_ipv4_addresses == (IP,)
    assert result.present_ipv4_addresses == ()
    assert result.missing_ipv4_addresses == (IP,)
    assert result.reason == f"dns_ipv4_missing_from_direct_ipset: {IP}"


def test_check_reports_ipset_read_failure_separately():
    result = SmartRoutingDomainDiagnosticService(
        make_executor(ipset_returncode=1, ipset_stdout="")
    ).check(DOMAIN)

    assert result.healthy is False
    assert result.direct_ipset_readable is False
    assert result.reason == "direct_ipset_unavailable_or_incomplete"


@pytest.mark.parametrize(
    ("override", "expected_reason"),
    [
        ({"marking_rule": False}, "direct_marking_rule_missing"),
        ({"policy_rule": False}, "direct_policy_rule_missing"),
        ({"forward_chain": False}, "direct_forward_chain_not_attached"),
        ({"forward_accept": False}, "direct_forward_accept_rule_missing"),
        ({"nat_chain": False}, "direct_nat_chain_not_attached"),
        ({"nat_masquerade": False}, "direct_nat_masquerade_rule_missing"),
    ],
)
def test_check_reports_missing_direct_datapath_component(override, expected_reason):
    result = SmartRoutingDomainDiagnosticService(make_executor(**override)).check(
        DOMAIN
    )

    assert result.healthy is False
    assert result.reason == expected_reason


def test_check_requires_marked_route_to_use_wan_interface():
    wrong_route = f"{IP} via 46.48.56.1 dev eth0 table 200 src 46.48.56.64 mark 0x64\n"
    result = SmartRoutingDomainDiagnosticService(
        make_executor(route_stdout=wrong_route)
    ).check(DOMAIN)

    assert result.healthy is False
    assert result.reason == "marked_route_verification_failed"
    assert result.route_results[0].endswith(" FAIL")


def test_check_reports_dns_failure():
    result = SmartRoutingDomainDiagnosticService(
        make_executor(dns_returncode=1, dns_stdout="")
    ).check(DOMAIN)

    assert result.healthy is False
    assert result.dns_ipv4_addresses == ()
    assert result.reason == "domain_dns_ipv4_not_found"


def test_invalid_domain_is_rejected():
    with pytest.raises(ValueError, match="at least two labels"):
        SmartRoutingDomainDiagnosticService(make_executor()).check("localhost")


def test_check_does_not_classify_unrelated_shared_ipset_members_as_stale():
    result = SmartRoutingDomainDiagnosticService(make_executor()).check(DOMAIN)

    assert result.healthy is True
    assert result.stale_ipv4_addresses == ()


def test_check_parses_ipset_members_with_timeout_suffix():
    ipset_output = (
        "Name: MAXVPN_DIRECT\n"
        "Type: hash:ip\n"
        "Header: family inet hashsize 1024 maxelem 65536 timeout 3600\n"
        "Members:\n"
        f"{IP} timeout 3593\n"
        "198.51.100.10 timeout 3599\n"
    )
    result = SmartRoutingDomainDiagnosticService(
        make_executor(ipset_stdout=ipset_output)
    ).check(DOMAIN)

    assert result.direct_ipset_readable is True
    assert result.present_ipv4_addresses == (IP,)
    assert result.missing_ipv4_addresses == ()
    assert result.healthy is True
    assert result.reason is None
