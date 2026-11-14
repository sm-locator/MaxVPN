from backend.models.command_result import CommandResult
from backend.services.smart_routing_dns_response_observer import (
    SmartRoutingDnsResponse,
    SmartRoutingDnsResponseObserver,
)


def result(stdout: str = "", returncode: int = 0) -> CommandResult:
    return CommandResult(
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


def test_parse_single_a_response():
    output = (
        "Sep 11 23:57:29 dnsmasq[28435]: "
        "11 127.0.0.1/37069 query[A] "
        "maxvpn-test.gps.navy from 127.0.0.1\n"
        "Sep 11 23:57:29 dnsmasq[28435]: "
        "11 127.0.0.1/37069 reply "
        "maxvpn-test.gps.navy is 81.90.181.120\n"
    )

    responses = SmartRoutingDnsResponseObserver._parse_responses(
        output,
        {"gps.navy"},
    )

    assert responses == (
        SmartRoutingDnsResponse(
            process_id=28435,
            transaction_id="11",
            domain="maxvpn-test.gps.navy",
            ipv4_addresses=("81.90.181.120",),
        ),
    )


def test_parse_multiple_a_records_as_one_response():
    output = (
        "Sep 11 23:57:29 dnsmasq[28435]: "
        "113 127.0.0.1/37069 query[A] example.gps.navy "
        "from 127.0.0.1\n"
        "Sep 11 23:57:29 dnsmasq[28435]: "
        "113 127.0.0.1/37069 reply example.gps.navy "
        "is 81.90.181.120\n"
        "Sep 11 23:57:29 dnsmasq[28435]: "
        "113 127.0.0.1/37069 reply example.gps.navy "
        "is 81.90.181.121\n"
    )

    responses = SmartRoutingDnsResponseObserver._parse_responses(
        output,
        {"gps.navy"},
    )

    assert responses[0].ipv4_addresses == (
        "81.90.181.120",
        "81.90.181.121",
    )


def test_parse_accepts_subdomain():
    output = (
        "Sep 11 23:57:29 dnsmasq[28435]: "
        "11 127.0.0.1/37069 query[A] "
        "api.gps.navy from 127.0.0.1\n"
        "Sep 11 23:57:29 dnsmasq[28435]: "
        "11 127.0.0.1/37069 reply "
        "api.gps.navy is 81.90.181.120\n"
    )

    responses = SmartRoutingDnsResponseObserver._parse_responses(
        output,
        {"gps.navy"},
    )

    assert responses[0].domain == "api.gps.navy"


def test_parse_rejects_unrelated_domain():
    output = (
        "Sep 11 23:57:29 dnsmasq[28435]: "
        "11 127.0.0.1/37069 query[A] "
        "example.com from 127.0.0.1\n"
        "Sep 11 23:57:29 dnsmasq[28435]: "
        "11 127.0.0.1/37069 reply "
        "example.com is 81.90.181.120\n"
    )

    assert (
        SmartRoutingDnsResponseObserver._parse_responses(
            output,
            {"gps.navy"},
        )
        == ()
    )


def test_parse_ignores_cname_and_collects_final_ipv4():
    output = (
        "Sep 11 23:57:29 dnsmasq[28435]: "
        "11 127.0.0.1/37069 query[A] "
        "example.gps.navy from 127.0.0.1\n"
        "Sep 11 23:57:29 dnsmasq[28435]: "
        "11 127.0.0.1/37069 reply "
        "example.gps.navy is <CNAME>\n"
        "Sep 11 23:57:29 dnsmasq[28435]: "
        "11 127.0.0.1/37069 reply "
        "target.example.gps.navy is 81.90.181.120\n"
    )

    responses = SmartRoutingDnsResponseObserver._parse_responses(
        output,
        {"gps.navy"},
    )

    assert responses[0].ipv4_addresses == ("81.90.181.120",)


def test_same_transaction_id_from_different_dnsmasq_processes_is_independent():
    output = (
        "Sep 12 00:10:00 dnsmasq[100]: "
        "11 127.0.0.1/10000 query[A] one.gps.navy from 127.0.0.1\n"
        "Sep 12 00:10:00 dnsmasq[200]: "
        "11 127.0.0.1/20000 query[A] two.gps.navy from 127.0.0.1\n"
        "Sep 12 00:10:00 dnsmasq[100]: "
        "11 127.0.0.1/10000 reply one.gps.navy is 81.90.181.10\n"
        "Sep 12 00:10:00 dnsmasq[200]: "
        "11 127.0.0.1/20000 reply two.gps.navy is 81.90.181.20\n"
    )

    responses = SmartRoutingDnsResponseObserver._parse_responses(
        output,
        {"gps.navy"},
    )

    assert responses == (
        SmartRoutingDnsResponse(
            process_id=100,
            transaction_id="11",
            domain="one.gps.navy",
            ipv4_addresses=("81.90.181.10",),
        ),
        SmartRoutingDnsResponse(
            process_id=200,
            transaction_id="11",
            domain="two.gps.navy",
            ipv4_addresses=("81.90.181.20",),
        ),
    )


def test_parse_lines_preserves_transaction_between_polling_cycles():
    observer = SmartRoutingDnsResponseObserver()

    query = (
        "Sep 12 00:20:00 dnsmasq[300]: "
        "42 127.0.0.1/10000 query[A] "
        "split.gps.navy from 127.0.0.1"
    )
    reply = (
        "Sep 12 00:20:00 dnsmasq[300]: "
        "42 127.0.0.1/10000 reply "
        "split.gps.navy is 81.90.181.120"
    )

    assert (
        observer.parse_lines(
            (query,),
            ("gps.navy",),
        )
        == ()
    )

    assert observer.parse_lines(
        (reply,),
        ("gps.navy",),
    ) == (
        SmartRoutingDnsResponse(
            process_id=300,
            transaction_id="42",
            domain="split.gps.navy",
            ipv4_addresses=("81.90.181.120",),
        ),
    )


def test_parse_lines_preserves_cname_transaction_between_polling_cycles():
    observer = SmartRoutingDnsResponseObserver()

    query = (
        "Sep 12 00:21:00 dnsmasq[301]: "
        "43 127.0.0.1/10001 query[A] "
        "cname.gps.navy from 127.0.0.1"
    )
    cname = (
        "Sep 12 00:21:00 dnsmasq[301]: "
        "43 127.0.0.1/10001 reply "
        "cname.gps.navy is <CNAME>"
    )
    final_a = (
        "Sep 12 00:21:00 dnsmasq[301]: "
        "43 127.0.0.1/10001 reply "
        "target.gps.navy is 81.90.181.121"
    )

    assert (
        observer.parse_lines(
            (query, cname),
            ("gps.navy",),
        )
        == ()
    )

    assert observer.parse_lines(
        (final_a,),
        ("gps.navy",),
    ) == (
        SmartRoutingDnsResponse(
            process_id=301,
            transaction_id="43",
            domain="cname.gps.navy",
            ipv4_addresses=("81.90.181.121",),
        ),
    )


def test_parse_single_aaaa_response():
    output = (
        "Sep 12 00:30:00 dnsmasq[400]: "
        "50 127.0.0.1/40000 query[AAAA] "
        "ipv6.gps.navy from 127.0.0.1\n"
        "Sep 12 00:30:00 dnsmasq[400]: "
        "50 127.0.0.1/40000 reply "
        "ipv6.gps.navy is 2001:db8::10\n"
    )

    responses = SmartRoutingDnsResponseObserver._parse_responses(
        output,
        {"gps.navy"},
    )

    assert responses == (
        SmartRoutingDnsResponse(
            process_id=400,
            transaction_id="50",
            domain="ipv6.gps.navy",
            ipv4_addresses=(),
            ipv6_addresses=("2001:db8::10",),
        ),
    )


def test_parse_multiple_aaaa_records_as_one_response():
    output = (
        "Sep 12 00:31:00 dnsmasq[401]: "
        "51 127.0.0.1/40001 query[AAAA] "
        "example.gps.navy from 127.0.0.1\n"
        "Sep 12 00:31:00 dnsmasq[401]: "
        "51 127.0.0.1/40001 reply "
        "example.gps.navy is 2001:db8::10\n"
        "Sep 12 00:31:00 dnsmasq[401]: "
        "51 127.0.0.1/40001 reply "
        "example.gps.navy is 2001:db8::11\n"
    )

    responses = SmartRoutingDnsResponseObserver._parse_responses(
        output,
        {"gps.navy"},
    )

    assert responses == (
        SmartRoutingDnsResponse(
            process_id=401,
            transaction_id="51",
            domain="example.gps.navy",
            ipv4_addresses=(),
            ipv6_addresses=("2001:db8::10", "2001:db8::11"),
        ),
    )


def test_parse_ignores_cname_and_collects_final_ipv6():
    output = (
        "Sep 12 00:32:00 dnsmasq[402]: "
        "52 127.0.0.1/40002 query[AAAA] "
        "example.gps.navy from 127.0.0.1\n"
        "Sep 12 00:32:00 dnsmasq[402]: "
        "52 127.0.0.1/40002 reply "
        "example.gps.navy is <CNAME>\n"
        "Sep 12 00:32:00 dnsmasq[402]: "
        "52 127.0.0.1/40002 reply "
        "target.example.gps.navy is 2001:db8::20\n"
    )

    responses = SmartRoutingDnsResponseObserver._parse_responses(
        output,
        {"gps.navy"},
    )

    assert responses == (
        SmartRoutingDnsResponse(
            process_id=402,
            transaction_id="52",
            domain="example.gps.navy",
            ipv4_addresses=(),
            ipv6_addresses=("2001:db8::20",),
        ),
    )


def test_parse_lines_preserves_aaaa_transaction_between_polling_cycles():
    observer = SmartRoutingDnsResponseObserver()

    query = (
        "Sep 12 00:33:00 dnsmasq[403]: "
        "53 127.0.0.1/40003 query[AAAA] "
        "split.gps.navy from 127.0.0.1"
    )
    reply = (
        "Sep 12 00:33:00 dnsmasq[403]: "
        "53 127.0.0.1/40003 reply "
        "split.gps.navy is 2001:db8::30"
    )

    assert (
        observer.parse_lines(
            (query,),
            ("gps.navy",),
        )
        == ()
    )

    assert observer.parse_lines(
        (reply,),
        ("gps.navy",),
    ) == (
        SmartRoutingDnsResponse(
            process_id=403,
            transaction_id="53",
            domain="split.gps.navy",
            ipv4_addresses=(),
            ipv6_addresses=("2001:db8::30",),
        ),
    )


def test_parse_lines_preserves_cname_aaaa_transaction_between_polling_cycles():
    observer = SmartRoutingDnsResponseObserver()

    query = (
        "Sep 12 00:34:00 dnsmasq[404]: "
        "54 127.0.0.1/40004 query[AAAA] "
        "cname.gps.navy from 127.0.0.1"
    )
    cname = (
        "Sep 12 00:34:00 dnsmasq[404]: "
        "54 127.0.0.1/40004 reply "
        "cname.gps.navy is <CNAME>"
    )
    final_aaaa = (
        "Sep 12 00:34:00 dnsmasq[404]: "
        "54 127.0.0.1/40004 reply "
        "target.gps.navy is 2001:db8::31"
    )

    assert (
        observer.parse_lines(
            (query, cname),
            ("gps.navy",),
        )
        == ()
    )

    assert observer.parse_lines(
        (final_aaaa,),
        ("gps.navy",),
    ) == (
        SmartRoutingDnsResponse(
            process_id=404,
            transaction_id="54",
            domain="cname.gps.navy",
            ipv4_addresses=(),
            ipv6_addresses=("2001:db8::31",),
        ),
    )


def test_incremental_responses_keep_log_order_instead_of_lexical_transaction_id():
    observer = SmartRoutingDnsResponseObserver()
    lines = (
        "Sep 12 00:40:00 dnsmasq[500]: "
        "20 127.0.0.1/50000 query[A] example.com from 127.0.0.1",
        "Sep 12 00:40:00 dnsmasq[500]: "
        "20 127.0.0.1/50000 reply example.com is 198.51.100.10",
        "Sep 12 00:41:00 dnsmasq[500]: "
        "100 127.0.0.1/50001 query[A] example.com from 127.0.0.1",
        "Sep 12 00:41:00 dnsmasq[500]: "
        "100 127.0.0.1/50001 reply example.com is 198.51.100.20",
    )

    responses = observer.parse_lines(lines, ("example.com",))

    assert [response.transaction_id for response in responses] == ["20", "100"]
    assert [response.ipv4_addresses for response in responses] == [
        ("198.51.100.10",),
        ("198.51.100.20",),
    ]


def test_parse_lines_marks_reused_transaction_id_with_different_domain_ambiguous():
    observer = SmartRoutingDnsResponseObserver()
    first_query = (
        "Sep 12 00:50:00 dnsmasq[600]: "
        "7 127.0.0.1/10000 query[A] first.gps.navy from 127.0.0.1"
    )
    second_query = (
        "Sep 12 00:50:01 dnsmasq[600]: "
        "7 127.0.0.1/10000 query[A] second.gps.navy from 127.0.0.1"
    )
    second_reply = (
        "Sep 12 00:50:02 dnsmasq[600]: "
        "7 127.0.0.1/10000 reply second.gps.navy is 81.90.181.77"
    )

    assert (
        observer.parse_lines(
            (first_query, second_query),
            ("gps.navy",),
        )
        == ()
    )

    # A conflicting ID must not silently change the owner of later replies.
    ambiguous = observer._pending[("600", "7")]
    assert ambiguous.domains == {"first.gps.navy", "second.gps.navy"}
    assert (
        observer.parse_lines(
            (second_reply,),
            ("gps.navy",),
        )
        == ()
    )

    observer.reset()
    assert observer._pending == {}


def test_prune_pending_expires_transaction_and_allows_transaction_id_reuse():
    observer = SmartRoutingDnsResponseObserver()
    transaction_key = ("610", "17")

    first_query = (
        "Sep 12 00:51:00 dnsmasq[610]: "
        "17 127.0.0.1/10001 query[A] first.gps.navy from 127.0.0.1"
    )
    observer.parse_lines((first_query,), ("gps.navy",))
    created_at = observer._pending[transaction_key].last_activity

    assert (
        observer.prune_pending(
            ("gps.navy",),
            now=created_at + observer.PENDING_TTL_SECONDS - 0.001,
        )
        == 0
    )
    assert transaction_key in observer._pending

    assert (
        observer.prune_pending(
            ("gps.navy",),
            now=created_at + observer.PENDING_TTL_SECONDS,
        )
        == 1
    )
    assert transaction_key not in observer._pending

    second_query = (
        "Sep 12 00:53:01 dnsmasq[610]: "
        "17 127.0.0.1/10001 query[A] second.gps.navy from 127.0.0.1"
    )
    second_reply = (
        "Sep 12 00:53:02 dnsmasq[610]: "
        "17 127.0.0.1/10001 reply second.gps.navy is 81.90.181.77"
    )

    assert observer.parse_lines(
        (second_query, second_reply),
        ("gps.navy",),
    ) == (
        SmartRoutingDnsResponse(
            process_id=610,
            transaction_id="17",
            domain="second.gps.navy",
            ipv4_addresses=("81.90.181.77",),
        ),
    )


def test_prune_pending_expires_ambiguous_transaction():
    observer = SmartRoutingDnsResponseObserver()
    first_query = (
        "Sep 12 00:54:00 dnsmasq[611]: "
        "18 127.0.0.1/10002 query[A] first.gps.navy from 127.0.0.1"
    )
    second_query = (
        "Sep 12 00:54:01 dnsmasq[611]: "
        "18 127.0.0.1/10002 query[A] second.gps.navy from 127.0.0.1"
    )

    observer.parse_lines(
        (first_query, second_query),
        ("gps.navy",),
    )
    ambiguous = observer._pending[("611", "18")]

    assert ambiguous.domains == {"first.gps.navy", "second.gps.navy"}
    assert (
        observer.prune_pending(
            ("gps.navy",),
            now=ambiguous.last_activity + observer.PENDING_TTL_SECONDS,
        )
        == 1
    )
    assert ("611", "18") not in observer._pending


def test_prune_pending_removes_transaction_outside_direct_policy():
    observer = SmartRoutingDnsResponseObserver()
    query = (
        "Sep 12 00:55:00 dnsmasq[612]: "
        "19 127.0.0.1/10003 query[A] stale.gps.navy from 127.0.0.1"
    )

    observer.parse_lines((query,), ("gps.navy",))

    assert observer.prune_pending(("other.example",)) == 1
    assert observer._pending == {}


def test_parse_lines_preserves_addresses_for_repeated_same_domain_query():
    observer = SmartRoutingDnsResponseObserver()
    query = (
        "Sep 12 00:51:00 dnsmasq[601]: "
        "8 127.0.0.1/10001 query[A] same.gps.navy from 127.0.0.1"
    )
    first_reply = (
        "Sep 12 00:51:01 dnsmasq[601]: "
        "8 127.0.0.1/10001 reply same.gps.navy is 81.90.181.80"
    )
    second_reply = (
        "Sep 12 00:51:02 dnsmasq[601]: "
        "8 127.0.0.1/10001 reply same.gps.navy is 81.90.181.81"
    )

    first = observer.parse_lines(
        (query, first_reply),
        ("gps.navy",),
    )
    assert first[0].ipv4_addresses == ("81.90.181.80",)

    second = observer.parse_lines(
        (query, second_reply),
        ("gps.navy",),
    )
    assert second == (
        SmartRoutingDnsResponse(
            process_id=601,
            transaction_id="8",
            domain="same.gps.navy",
            ipv4_addresses=("81.90.181.80", "81.90.181.81"),
        ),
    )


def test_parse_lines_bounds_pending_transaction_count(monkeypatch):
    monkeypatch.setattr(
        SmartRoutingDnsResponseObserver,
        "MAX_PENDING",
        2,
        raising=False,
    )
    observer = SmartRoutingDnsResponseObserver()

    lines = tuple(
        (
            f"Sep 12 00:52:0{transaction_id} dnsmasq[602]: "
            f"{transaction_id} 127.0.0.1/10002 query[A] "
            f"host-{transaction_id}.gps.navy from 127.0.0.1"
        )
        for transaction_id in (1, 2, 3)
    )

    observer.parse_lines(lines, ("gps.navy",))

    assert tuple(observer._pending) == (("602", "2"), ("602", "3"))
