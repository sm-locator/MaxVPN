from backend.services.smart_routing_dependency_diagnostic import (
    DependencyDiagnosticResource,
)
from backend.services.smart_routing_dependency_diagnostic_service import (
    SmartRoutingDependencyDiagnosticService,
)


def resource(
    hostname: str,
    *,
    ips: tuple[str, ...] = (),
    cname_chain: tuple[str, ...] = (),
    queries: int = 1,
    query_times: tuple[int, ...] = (),
) -> DependencyDiagnosticResource:
    return DependencyDiagnosticResource(
        hostname=hostname,
        ips=ips,
        cname_chain=cname_chain or (hostname,),
        query_count=queries,
        query_times=query_times,
    )


def test_same_site_dependencies_are_grouped_under_site_domain():
    service = SmartRoutingDependencyDiagnosticService()

    result = service.analyze(
        "2GIS.RU.",
        [
            resource(
                "2gis.ru",
                ips=("91.236.49.1",),
            ),
            resource(
                "maps.2gis.com",
                ips=("91.236.49.2",),
            ),
            resource(
                "tile3.maps.2gis.com",
                ips=("91.236.49.3",),
            ),
        ],
        direct_ips=(
            "91.236.49.1",
            "91.236.49.2",
            "91.236.49.3",
        ),
        direct_rules=(
            "2gis.ru",
            "maps.2gis.com",
        ),
    )

    assert result.site_domain == "2gis.ru"
    assert len(result.resources) == 3

    maps = next(item for item in result.resources if item.hostname == "maps.2gis.com")

    assert maps.relation == "external"
    assert maps.routing == "direct"
    assert maps.covered_by_rule is True
    assert maps.rule_domain == "maps.2gis.com"


def test_uncovered_vpn_dependency_becomes_candidate_for_direct():
    service = SmartRoutingDependencyDiagnosticService()

    result = service.analyze(
        "2gis.ru",
        [
            resource(
                "photo.2gis.com",
                ips=("91.240.170.190",),
            ),
            resource(
                "jam.api.2gis.com",
                ips=("203.0.113.10",),
            ),
        ],
        direct_ips=("91.240.170.190",),
        direct_rules=("2gis.ru",),
    )

    photo = next(item for item in result.resources if item.hostname == "photo.2gis.com")
    jam = next(item for item in result.resources if item.hostname == "jam.api.2gis.com")

    assert photo.routing == "direct"
    assert photo.covered_by_rule is False
    assert photo.candidate_for_direct is False

    assert jam.routing == "vpn"
    assert jam.covered_by_rule is False
    assert jam.candidate_for_direct is True


def test_partial_routing_is_reported_when_only_some_ips_are_direct():
    service = SmartRoutingDependencyDiagnosticService()

    result = service.analyze(
        "example.com",
        [
            resource(
                "cdn.example.net",
                ips=(
                    "203.0.113.10",
                    "198.51.100.10",
                ),
            ),
        ],
        direct_ips=("203.0.113.10",),
    )

    item = result.resources[0]

    assert item.routing == "partial"
    assert item.candidate_for_direct is False
    assert item.selection_allowed is False


def test_external_dependency_is_marked_external():
    service = SmartRoutingDependencyDiagnosticService()

    result = service.analyze(
        "2gis.ru",
        [
            resource(
                "qac0vv2gz0.a.trbcdn.net",
                ips=("91.240.170.190",),
            ),
        ],
    )

    item = result.resources[0]

    assert item.relation == "external"
    assert item.routing == "vpn"
    assert item.category == "background"
    assert item.candidate_for_direct is False


def test_most_specific_rule_is_selected():
    service = SmartRoutingDependencyDiagnosticService()

    result = service.analyze(
        "example.com",
        [
            resource(
                "api.example.com",
                ips=("203.0.113.10",),
            ),
        ],
        direct_rules=(
            "example.com",
            "api.example.com",
        ),
    )

    item = result.resources[0]

    assert item.covered_by_rule is True
    assert item.rule_domain == "api.example.com"


def test_summary_counts_resources():
    service = SmartRoutingDependencyDiagnosticService()

    result = service.analyze(
        "example.com",
        [
            resource("example.com", ips=("203.0.113.1",)),
            resource("api.example.com", ips=("203.0.113.2",)),
            resource("cdn.example.net", ips=("198.51.100.10",)),
            resource("unknown.example.net"),
        ],
        direct_ips=(
            "203.0.113.1",
            "203.0.113.2",
        ),
        direct_rules=("example.com",),
    )

    assert result.summary.observed == 4
    assert result.summary.direct == 2
    assert result.summary.vpn == 1
    assert result.summary.unknown == 1
    assert result.summary.uncovered == 2


def test_analyze_creates_maps_dependency_from_repeated_subdomains() -> None:
    service = SmartRoutingDependencyDiagnosticService()

    resources = [
        DependencyDiagnosticResource(
            hostname="tile0.maps.2gis.com",
            ips=("91.236.49.2",),
            cname_chain=(
                "tile0.maps.2gis.com",
                "origin-tile0.maps.2gis.com",
            ),
            query_count=2,
        ),
        DependencyDiagnosticResource(
            hostname="tile1.maps.2gis.com",
            ips=("91.236.49.2",),
            cname_chain=(
                "tile1.maps.2gis.com",
                "tile0.maps.2gis.com",
                "origin-tile0.maps.2gis.com",
            ),
            query_count=1,
        ),
        DependencyDiagnosticResource(
            hostname="tile2.maps.2gis.com",
            ips=("91.236.49.2",),
            cname_chain=(
                "tile2.maps.2gis.com",
                "tile0.maps.2gis.com",
                "origin-tile0.maps.2gis.com",
            ),
            query_count=1,
        ),
    ]

    result = service.analyze(
        "2gis.ru",
        resources,
        direct_ips=(),
        direct_rules=("2gis.ru",),
    )

    aggregate = next(
        item for item in result.resources if item.hostname == "maps.2gis.com"
    )

    assert aggregate.synthetic is True
    assert aggregate.ips == ("91.236.49.2",)
    assert aggregate.query_count == 4
    assert aggregate.routing == "vpn"
    assert aggregate.covered_by_rule is False
    assert aggregate.candidate_for_direct is False
    assert aggregate.selection_allowed is False
    assert aggregate.observed_hostnames == (
        "tile0.maps.2gis.com",
        "tile1.maps.2gis.com",
        "tile2.maps.2gis.com",
    )

    # Synthetic resources must not inflate the observed DNS count.
    assert result.summary.observed == 3


def test_analyze_does_not_create_broader_parent_dependency() -> None:
    service = SmartRoutingDependencyDiagnosticService()

    resources = [
        resource("tile0.maps.2gis.com"),
        resource("tile1.maps.2gis.com"),
        resource("i1.photo.2gis.com"),
        resource("i2.photo.2gis.com"),
    ]

    result = service.analyze(
        "2gis.ru",
        resources,
        direct_rules=("2gis.ru",),
    )

    hostnames = {item.hostname for item in result.resources}

    assert "maps.2gis.com" in hostnames
    assert "photo.2gis.com" in hostnames
    assert "2gis.com" not in hostnames

    maps = next(item for item in result.resources if item.hostname == "maps.2gis.com")
    photo = next(item for item in result.resources if item.hostname == "photo.2gis.com")

    assert maps.synthetic is True
    assert photo.synthetic is True

    assert maps.observed_hostnames == (
        "tile0.maps.2gis.com",
        "tile1.maps.2gis.com",
    )
    assert photo.observed_hostnames == (
        "i1.photo.2gis.com",
        "i2.photo.2gis.com",
    )


def test_timed_external_candidate_is_visible_but_not_selectable():
    service = SmartRoutingDependencyDiagnosticService()
    result = service.analyze(
        "2gis.ru",
        [
            resource("2gis.ru", ips=("95.129.232.210",), query_times=(100,)),
            resource(
                "analytics.example.net", ips=("198.51.100.22",), query_times=(105,)
            ),
            resource("old.example.net", ips=("198.51.100.23",), query_times=(130,)),
        ],
    )
    timed = next(
        item for item in result.resources if item.hostname == "analytics.example.net"
    )
    old = next(item for item in result.resources if item.hostname == "old.example.net")
    assert timed.category == "external_candidate"
    assert timed.candidate_for_direct is False
    assert old.category == "background"
    assert old.candidate_for_direct is False


def test_known_2gis_brand_alias_is_selectable_when_uncovered_and_vpn_routed():
    service = SmartRoutingDependencyDiagnosticService()
    result = service.analyze(
        "2gis.ru",
        [resource("jam.api.2gis.com", ips=("91.236.49.1",))],
        direct_ips=(),
        direct_rules=(),
    )
    item = next(
        item for item in result.resources if item.hostname == "jam.api.2gis.com"
    )
    assert item.category == "external_candidate"
    assert item.brand_alias is True
    assert item.routing == "vpn"
    assert item.selection_allowed is True
    assert item.candidate_for_direct is True


def test_windows_connectivity_and_reverse_dns_are_background_even_when_time_related():
    service = SmartRoutingDependencyDiagnosticService()
    result = service.analyze(
        "2gis.ru",
        [
            resource("2gis.ru", ips=("95.129.232.210",), query_times=(86398,)),
            resource("www.msftconnecttest.com", ips=("13.107.4.52",), query_times=(2,)),
            resource("4.3.2.1.in-addr.arpa", query_times=(86399,)),
        ],
    )
    windows = next(
        item for item in result.resources if item.hostname == "www.msftconnecttest.com"
    )
    reverse = next(
        item for item in result.resources if item.hostname == "4.3.2.1.in-addr.arpa"
    )
    assert windows.category == "background"
    assert reverse.category == "background"
    assert windows.selection_allowed is False
    assert reverse.selection_allowed is False


def test_time_relation_wraps_across_midnight():
    service = SmartRoutingDependencyDiagnosticService()
    result = service.analyze(
        "2gis.ru",
        [
            resource("2gis.ru", ips=("95.129.232.210",), query_times=(86398,)),
            resource("telemetry.example.net", ips=("198.51.100.55",), query_times=(2,)),
        ],
    )
    telemetry = next(
        item for item in result.resources if item.hostname == "telemetry.example.net"
    )
    assert telemetry.category == "external_candidate"
    assert telemetry.candidate_for_direct is False


def test_only_ipv4_evidence_can_be_selected():
    service = SmartRoutingDependencyDiagnosticService()
    result = service.analyze(
        "2gis.ru",
        [resource("jam.api.2gis.com", ips=("2001:db8::1",))],
    )
    item = next(
        item for item in result.resources if item.hostname == "jam.api.2gis.com"
    )
    assert item.ips == ()
    assert item.routing == "unknown"
    assert item.selection_allowed is False


def test_commit_revalidation_rejects_changed_route_rule_and_synthetic_resources():
    checker = SmartRoutingDependencyDiagnosticService.is_selectable_now
    base = {
        "hostname": "jam.api.2gis.com",
        "site_domain": "2gis.ru",
        "ips": ("91.236.49.1",),
        "direct_ips": (),
        "direct_rules": (),
        "synthetic": False,
    }
    assert checker(**base) is True
    assert checker(**{**base, "direct_ips": ("91.236.49.1",)}) is False
    assert checker(**{**base, "direct_rules": ("2gis.com",)}) is False
    assert checker(**{**base, "synthetic": True}) is False
    assert checker(**{**base, "hostname": "clients4.google.com"}) is False


def test_time_relation_includes_exactly_five_seconds():
    service = SmartRoutingDependencyDiagnosticService()
    result = service.analyze(
        "2gis.ru",
        [
            resource("2gis.ru", ips=("95.129.232.210",), query_times=(100,)),
            resource(
                "analytics.example.net",
                ips=("198.51.100.22",),
                query_times=(105,),
            ),
        ],
    )

    item = next(
        item for item in result.resources if item.hostname == "analytics.example.net"
    )
    assert item.category == "external_candidate"


def test_time_relation_excludes_six_seconds():
    service = SmartRoutingDependencyDiagnosticService()
    result = service.analyze(
        "2gis.ru",
        [
            resource("2gis.ru", ips=("95.129.232.210",), query_times=(100,)),
            resource(
                "analytics.example.net",
                ips=("198.51.100.22",),
                query_times=(106,),
            ),
        ],
    )

    item = next(
        item for item in result.resources if item.hostname == "analytics.example.net"
    )
    assert item.category == "background"
