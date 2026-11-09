from backend.services.smart_routing_dependency_diagnostic import (
    SmartRoutingDependencyDnsParser,
)
from backend.services.smart_routing_dependency_diagnostic_session import (
    SmartRoutingDependencyDiagnosticSessionService,
)


def line(text: str) -> str:
    return f"dnsmasq[1234]: 12:00:00 host/53 {text}"


def test_query_and_reply_split_across_chunks_are_correlated():
    parser = SmartRoutingDependencyDnsParser()

    parser.feed(line("query[A] maps.2gis.com from 192.168.31.100"))

    parser.feed(line("reply maps.2gis.com is 91.236.49.2"))

    resources = parser.resources(client_ip="192.168.31.100")

    assert len(resources) == 1
    assert resources[0].hostname == "maps.2gis.com"
    assert resources[0].ips == ("91.236.49.2",)
    assert resources[0].query_count == 1


def test_cname_chain_is_preserved():
    parser = SmartRoutingDependencyDnsParser()

    parser.feed(
        "\n".join(
            [
                line("query[A] tile3.maps.2gis.com from 192.168.31.100"),
                line("reply tile3.maps.2gis.com is tile0.maps.2gis.com"),
                line("query[A] tile0.maps.2gis.com from 192.168.31.100"),
                line("reply tile0.maps.2gis.com is origin-tile0.maps.2gis.com"),
                line("query[A] origin-tile0.maps.2gis.com from 192.168.31.100"),
                line("reply origin-tile0.maps.2gis.com is 91.236.49.2"),
            ]
        )
    )

    resources = parser.resources(client_ip="192.168.31.100")

    assert len(resources) == 3

    tile = next(item for item in resources if item.hostname == "tile3.maps.2gis.com")

    assert tile.cname_chain == (
        "tile3.maps.2gis.com",
        "tile0.maps.2gis.com",
        "origin-tile0.maps.2gis.com",
    )
    assert tile.ips == ("91.236.49.2",)


def test_transactional_cname_hops_keep_original_a_query_until_terminal_ipv4():
    parser = SmartRoutingDependencyDnsParser()
    parser.feed(
        "\n".join(
            [
                (
                    "Sep 16 16:50:01 dnsmasq[1234]: 7 192.168.31.1/53 "
                    "query[A] filekeeper-vod.2gis.com from 192.168.31.100"
                ),
                (
                    "Sep 16 16:50:02 dnsmasq[1234]: 7 192.168.31.1/53 "
                    "reply filekeeper-vod.2gis.com is edge-1.cdn.example.net"
                ),
                (
                    "Sep 16 16:50:02 dnsmasq[1234]: 7 192.168.31.1/53 "
                    "reply edge-1.cdn.example.net is edge-2.cdn.example.net"
                ),
                (
                    "Sep 16 16:50:03 dnsmasq[1234]: 7 "
                    "192.168.31.1/53 reply edge-2.cdn.example.net is 185.253.21.13"
                ),
            ]
        )
    )

    resources = parser.resources(client_ip="192.168.31.100")
    item = next(
        resource
        for resource in resources
        if resource.hostname == "filekeeper-vod.2gis.com"
    )

    assert item.ips == ("185.253.21.13",)
    assert item.cname_chain == (
        "filekeeper-vod.2gis.com",
        "edge-1.cdn.example.net",
        "edge-2.cdn.example.net",
    )


def test_client_filter_excludes_other_client():
    parser = SmartRoutingDependencyDnsParser()

    parser.feed(
        "\n".join(
            [
                line("query[A] maps.2gis.com from 192.168.31.100"),
                line("reply maps.2gis.com is 91.236.49.2"),
                line("query[A] maps.2gis.com from 192.168.31.101"),
                line("reply maps.2gis.com is 91.236.49.3"),
            ]
        )
    )

    resources = parser.resources(client_ip="192.168.31.100")

    assert len(resources) == 1
    assert resources[0].ips == ("91.236.49.2",)


def test_queries_are_counted():
    parser = SmartRoutingDependencyDnsParser()

    parser.feed(
        "\n".join(
            [
                line("query[A] photo.2gis.com from 192.168.31.100"),
                line("reply photo.2gis.com is 91.240.170.190"),
                line("query[A] photo.2gis.com from 192.168.31.100"),
                line("reply photo.2gis.com is 91.231.235.126"),
            ]
        )
    )

    resources = parser.resources(client_ip="192.168.31.100")

    assert resources[0].query_count == 2
    assert resources[0].ips == (
        "91.231.235.126",
        "91.240.170.190",
    )


def test_parser_preserves_query_timestamps_and_supports_https_without_ipv4_answer():
    parser = SmartRoutingDependencyDnsParser()
    parser.feed(
        "\n".join(
            [
                (
                    "Sep 16 16:50:01 dnsmasq[1234]: 7 "
                    "192.168.31.1/53 query[HTTPS] maps.2gis.com from 192.168.31.100"
                ),
                (
                    "Sep 16 16:50:02 dnsmasq[1234]: 8 "
                    "192.168.31.1/53 query[A] maps.2gis.com from 192.168.31.100"
                ),
                (
                    "Sep 16 16:50:02 dnsmasq[1234]: 7 "
                    "192.168.31.1/53 reply maps.2gis.com is NODATA"
                ),
                (
                    "Sep 16 16:50:02 dnsmasq[1234]: 8 "
                    "192.168.31.1/53 reply maps.2gis.com is 91.236.49.2"
                ),
            ]
        )
    )
    item = parser.resources(client_ip="192.168.31.100")[0]
    assert item.hostname == "maps.2gis.com"
    assert item.ips == ("91.236.49.2",)
    assert item.query_count == 2
    assert item.query_times == (16 * 3600 + 50 * 60 + 1, 16 * 3600 + 50 * 60 + 2)


def test_transaction_ids_keep_same_hostname_replies_isolated_between_clients():
    parser = SmartRoutingDependencyDnsParser()
    parser.feed(
        "\n".join(
            [
                (
                    "Sep 16 16:50:01 dnsmasq[1234]: 7 "
                    "192.168.31.1/53 query[A] maps.2gis.com from 192.168.31.100"
                ),
                (
                    "Sep 16 16:50:01 dnsmasq[1234]: 8 "
                    "192.168.31.1/53 query[A] maps.2gis.com from 192.168.31.101"
                ),
                (
                    "Sep 16 16:50:02 dnsmasq[1234]: 8 "
                    "192.168.31.1/53 reply maps.2gis.com is 91.236.49.99"
                ),
                (
                    "Sep 16 16:50:02 dnsmasq[1234]: 7 "
                    "192.168.31.1/53 reply maps.2gis.com is 91.236.49.2"
                ),
            ]
        )
    )
    a = parser.resources(client_ip="192.168.31.100")[0]
    b = parser.resources(client_ip="192.168.31.101")[0]
    assert a.ips == ("91.236.49.2",)
    assert b.ips == ("91.236.49.99",)


def test_session_filter_preserves_non_a_dns_queries_for_target_client():
    lines = (
        (
            "dnsmasq[1234]: 7 192.168.31.1/53 "
            "query[HTTPS] maps.2gis.com from 192.168.31.100"
        ),
        (
            "dnsmasq[1234]: 8 192.168.31.1/53 "
            "query[AAAA] maps.2gis.com from 192.168.31.101"
        ),
        "dnsmasq[1234]: 7 192.168.31.1/53 reply maps.2gis.com is NODATA",
    )

    filtered = SmartRoutingDependencyDiagnosticSessionService._filter_client_lines(
        lines, "192.168.31.100"
    )

    assert len(filtered) == 2
    assert "query[HTTPS]" in filtered[0]
    # Replies have no client-IP field; they are retained for transaction correlation.
    assert "reply maps.2gis.com" in filtered[1]


def test_https_nodata_without_transaction_id_does_not_consume_a_reply():
    parser = SmartRoutingDependencyDnsParser()
    parser.feed(
        "\n".join(
            [
                line("query[HTTPS] maps.2gis.com from 192.168.31.100"),
                line("query[A] maps.2gis.com from 192.168.31.100"),
                line("reply maps.2gis.com is NODATA"),
                line("reply maps.2gis.com is 91.236.49.2"),
            ]
        )
    )

    resources = parser.resources(client_ip="192.168.31.100")
    item = next(
        resource for resource in resources if resource.hostname == "maps.2gis.com"
    )
    assert item.ips == ("91.236.49.2",)
    assert item.query_count == 2


def test_transactional_cached_a_reply_is_correlated_to_client():
    parser = SmartRoutingDependencyDnsParser()
    parser.feed(
        "\n".join(
            [
                (
                    "Oct 19 22:57:58 dnsmasq[22762]: 32849 "
                    "192.168.8.231/65105 query[A] jam.api.2gis.com from 192.168.8.231"
                ),
                (
                    "Oct 19 22:57:58 dnsmasq[22762]: 32849 "
                    "192.168.8.231/65105 cached jam.api.2gis.com is 91.236.49.1"
                ),
            ]
        )
    )

    resources = parser.resources(client_ip="192.168.8.231")
    item = next(
        resource for resource in resources if resource.hostname == "jam.api.2gis.com"
    )

    assert item.ips == ("91.236.49.1",)
    assert item.query_count == 1


def test_transactional_cached_cname_terminal_ipv4_is_attached_to_original_alias():
    parser = SmartRoutingDependencyDnsParser()
    parser.feed(
        "\n".join(
            [
                (
                    "Oct 19 22:57:59 dnsmasq[22762]: 32850 "
                    "192.168.8.231/65105 query[A] "
                    "filekeeper-vod.2gis.com from 192.168.8.231"
                ),
                (
                    "Oct 19 22:57:59 dnsmasq[22762]: 32850 "
                    "192.168.8.231/65105 cached filekeeper-vod.2gis.com is <CNAME>"
                ),
                (
                    "Oct 19 22:57:59 dnsmasq[22762]: 32850 "
                    "192.168.8.231/65105 cached "
                    "p28431.clients-cdnnow.ru is 185.253.21.13"
                ),
            ]
        )
    )

    resources = parser.resources(client_ip="192.168.8.231")
    item = next(
        resource
        for resource in resources
        if resource.hostname == "filekeeper-vod.2gis.com"
    )

    assert item.ips == ("185.253.21.13",)
    assert item.query_count == 1


def test_legacy_cached_a_reply_without_transaction_metadata_is_correlated():
    parser = SmartRoutingDependencyDnsParser()
    parser.feed(
        "\n".join(
            [
                line("query[A] jam.api.2gis.com from 192.168.8.231"),
                line("cached jam.api.2gis.com is 91.236.49.1"),
            ]
        )
    )

    resources = parser.resources(client_ip="192.168.8.231")
    item = next(
        resource for resource in resources if resource.hostname == "jam.api.2gis.com"
    )

    assert item.ips == ("91.236.49.1",)
    assert item.query_count == 1
