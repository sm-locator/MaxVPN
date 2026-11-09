from unittest.mock import Mock

from backend.services.smart_routing_dependency_diagnostic_service import (
    SmartRoutingDependencyDiagnosticService,
)
from backend.services.smart_routing_dependency_diagnostic_session import (
    SmartRoutingDependencyDiagnosticSessionService,
)
from backend.services.smart_routing_dns_log_reader import (
    SmartRoutingDnsLogCursor,
    SmartRoutingDnsLogReadResult,
)


def command_result(stdout: str = "", returncode: int = 0, stderr: str = ""):
    return Mock(
        stdout=stdout,
        returncode=returncode,
        stderr=stderr,
    )


def dns_line(payload: str) -> str:
    return f"Sep 16 16:50:01 dnsmasq[1234]: 7 192.168.31.1/53 {payload}"


class FakeReader:
    def __init__(self, batches):
        self._batches = iter(batches)
        self._cursor = SmartRoutingDnsLogCursor(12345, 1000)

    def current_cursor(self):
        return self._cursor

    def read(self, cursor):
        try:
            lines = next(self._batches)
        except StopIteration:
            lines = ()

        self._cursor = SmartRoutingDnsLogCursor(
            cursor.inode,
            cursor.offset + sum(len(line.encode("utf-8")) + 1 for line in lines),
        )

        return SmartRoutingDnsLogReadResult(
            lines=tuple(lines),
            cursor=self._cursor,
            reset=False,
        )


def test_full_2gis_dependency_flow():
    client_ip = "192.168.31.100"

    batches = [
        (
            dns_line("7 192.168.31.100/53 query[A] 2gis.ru from 192.168.31.100"),
            dns_line(
                "7 192.168.31.100/53 query[A] tile3.maps.2gis.com from 192.168.31.100"
            ),
            dns_line("7 192.168.31.100/53 reply 2gis.ru is 91.236.49.1"),
        ),
        (
            dns_line(
                "8 192.168.31.100/53 reply tile3.maps.2gis.com is tile0.maps.2gis.com"
            ),
            dns_line(
                "8 192.168.31.100/53 query[A] tile0.maps.2gis.com from 192.168.31.100"
            ),
            dns_line(
                "8 192.168.31.100/53 reply "
                "tile0.maps.2gis.com is "
                "origin-tile0.maps.2gis.com"
            ),
        ),
        (
            dns_line(
                "9 192.168.31.100/53 query[A] "
                "origin-tile0.maps.2gis.com from 192.168.31.100"
            ),
            dns_line(
                "9 192.168.31.100/53 reply origin-tile0.maps.2gis.com is 91.236.49.2"
            ),
            dns_line("9 192.168.31.100/53 query[A] photo.2gis.com from 192.168.31.100"),
            dns_line("9 192.168.31.100/53 reply photo.2gis.com is 91.240.170.190"),
            dns_line(
                "9 192.168.31.100/53 query[A] "
                "qac0vv2gz0.a.trbcdn.net "
                "from 192.168.31.100"
            ),
            dns_line(
                "9 192.168.31.100/53 reply qac0vv2gz0.a.trbcdn.net is 91.231.235.126"
            ),
        ),
    ]

    reader = FakeReader(batches)
    analyzer = SmartRoutingDependencyDiagnosticService()

    session_service = SmartRoutingDependencyDiagnosticSessionService(
        reader=reader,
        analyzer=analyzer,
    )

    started = session_service.start(
        site_domain="2GIS.RU.",
        client_ip=client_ip,
        duration_seconds=30,
    )

    assert started["site_domain"] == "2gis.ru"

    direct_ips = {
        "91.236.49.1",
        "91.236.49.2",
    }

    direct_rules = (
        "2gis.ru",
        "maps.2gis.com",
    )

    payload, group = session_service.poll(
        started["token"],
        direct_ips=direct_ips,
        direct_rules=direct_rules,
    )

    payload, group = session_service.poll(
        started["token"],
        direct_ips=direct_ips,
        direct_rules=direct_rules,
    )

    payload, group = session_service.poll(
        started["token"],
        direct_ips=direct_ips,
        direct_rules=direct_rules,
    )

    assert payload["site_domain"] == "2gis.ru"
    assert payload["client_ip"] == client_ip

    names = {item.hostname for item in group.resources}

    assert "2gis.ru" in names
    assert "tile3.maps.2gis.com" in names
    assert "tile0.maps.2gis.com" in names
    assert "origin-tile0.maps.2gis.com" in names
    assert "photo.2gis.com" in names
    assert "qac0vv2gz0.a.trbcdn.net" in names

    tile = next(
        item for item in group.resources if item.hostname == "tile3.maps.2gis.com"
    )

    assert tile.routing == "direct"
    assert tile.covered_by_rule is True
    assert tile.rule_domain == "maps.2gis.com"
    assert tile.cname_chain == (
        "tile3.maps.2gis.com",
        "tile0.maps.2gis.com",
        "origin-tile0.maps.2gis.com",
    )

    photo = next(item for item in group.resources if item.hostname == "photo.2gis.com")

    assert photo.routing == "vpn"
    assert photo.covered_by_rule is False
    assert photo.candidate_for_direct is True

    cdn = next(
        item for item in group.resources if item.hostname == "qac0vv2gz0.a.trbcdn.net"
    )

    assert cdn.routing == "vpn"
    assert cdn.relation == "external"
    assert cdn.category == "external_candidate"
    assert cdn.candidate_for_direct is False

    assert group.summary.observed == 6
    assert group.summary.vpn == 2
    assert group.summary.uncovered == 2


def test_full_flow_keeps_clients_isolated():
    client_a = "192.168.31.100"
    client_b = "192.168.31.101"

    batches = [
        (
            dns_line(f"10 192.168.31.100/53 query[A] maps.2gis.com from {client_a}"),
            dns_line("10 192.168.31.100/53 reply maps.2gis.com is 91.236.49.2"),
            dns_line(f"11 192.168.31.101/53 query[A] maps.2gis.com from {client_b}"),
            dns_line("11 192.168.31.101/53 reply maps.2gis.com is 91.236.49.99"),
        ),
    ]

    reader = FakeReader(batches)
    session_service = SmartRoutingDependencyDiagnosticSessionService(
        reader=reader,
        analyzer=SmartRoutingDependencyDiagnosticService(),
    )

    started = session_service.start(
        site_domain="2gis.ru",
        client_ip=client_a,
        duration_seconds=30,
    )

    _, group = session_service.poll(
        started["token"],
        direct_ips={"91.236.49.2"},
        direct_rules=(),
    )

    maps = next(item for item in group.resources if item.hostname == "maps.2gis.com")

    assert maps.ips == ("91.236.49.2",)
    assert maps.routing == "direct"
