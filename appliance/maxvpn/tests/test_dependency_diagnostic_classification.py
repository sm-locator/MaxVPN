from pathlib import Path
from unittest.mock import patch
import time

with patch.object(Path, "mkdir"):
    from appliance.maxvpn import server as appliance

CLIENT = "192.168.8.231"


def query_line(
    query_id,
    hostname,
    *,
    qtype="A",
    client=CLIENT,
    peer=None,
    timestamp="Oct 19 23:05:44",
    pid="22762",
):
    peer = peer or f"{client}/52360"
    return (
        f"{timestamp} dnsmasq[{pid}]: {query_id} {peer} "
        f"query[{qtype}] {hostname} from {client}"
    )


def answer_line(
    query_id,
    action,
    hostname,
    answer,
    *,
    client=CLIENT,
    peer=None,
    timestamp="Oct 19 23:05:44",
    pid="22762",
):
    peer = peer or f"{client}/52360"
    return (
        f"{timestamp} dnsmasq[{pid}]: {query_id} {peer} {action} {hostname} is {answer}"
    )


def test_parser_tracks_a_aaaa_https_queries_and_times():
    lines = [
        query_line("100", "www.example.org", qtype="A", timestamp="Oct 19 23:05:44"),
        query_line("101", "www.example.org", qtype="AAAA", timestamp="Oct 19 23:05:45"),
        query_line(
            "102", "www.example.org", qtype="HTTPS", timestamp="Oct 19 23:05:46"
        ),
    ]
    _, resources = appliance._diagnostic_parse(
        "\n".join(lines),
        CLIENT,
        parser_state={"transactions": {}, "selected_client_ip": CLIENT},
    )
    item = next(row for row in resources if row["hostname"] == "www.example.org")
    assert item["queries"] == 3
    assert item["ips"] == []
    assert item["query_times"] == [83144, 83145, 83146]


def test_non_a_query_does_not_attach_ipv4_answer_as_a_record():
    query = query_line("103", "www.example.org", qtype="AAAA")
    reply = answer_line("103", "reply", "www.example.org", "93.184.216.34")
    _, resources = appliance._diagnostic_parse(query + "\n" + reply, CLIENT)
    item = next(row for row in resources if row["hostname"] == "www.example.org")
    assert item["ips"] == []


def test_time_of_day_helper_and_midnight_wrap():
    assert (
        appliance._diagnostic_time_of_day("Oct 19 23:05:44 dnsmasq[1]: event") == 83144
    )
    assert appliance._diagnostic_time_of_day("not a syslog timestamp") is None
    classified = appliance._diagnostic_classify_resource(
        "cdn.vendor.net",
        ["203.0.113.7"],
        set(),
        [],
        "example.org",
        query_times=[2],
        target_times={86398},
        relation_window_seconds=5,
    )
    assert classified["category"] == "external_candidate"
    assert classified["candidate_for_direct"] is False


def test_external_domain_within_five_seconds_is_view_only_candidate():
    classified = appliance._diagnostic_classify_resource(
        "cdn.vendor.net",
        ["203.0.113.7"],
        set(),
        [],
        "example.org",
        query_times=[83149],
        target_times={83144},
        relation_window_seconds=5,
    )
    assert classified["category"] == "external_candidate"
    assert "в пределах 5 секунд" in classified["role"]
    assert classified["route"] == "vpn"
    assert classified["candidate_for_direct"] is False


def test_external_domain_outside_time_window_is_background():
    classified = appliance._diagnostic_classify_resource(
        "cdn.vendor.net",
        ["203.0.113.7"],
        set(),
        [],
        "example.org",
        query_times=[83150],
        target_times={83144},
        relation_window_seconds=5,
    )
    assert classified["category"] == "background"


def test_windows_connectivity_and_reverse_dns_are_background():
    for hostname in (
        "www.msftconnecttest.com",
        "dns.msftncsi.com",
        "8.8.8.8.in-addr.arpa",
        "b.a.ip6.arpa",
    ):
        classified = appliance._diagnostic_classify_resource(
            hostname,
            ["203.0.113.7"],
            set(),
            [],
            "example.org",
            query_times=[83144],
            target_times={83144},
        )
        assert classified["category"] == "background", hostname
        assert classified["candidate_for_direct"] is False


def test_mixed_route_is_explicit_and_not_selectable():
    classified = appliance._diagnostic_classify_resource(
        "static.example.org",
        ["203.0.113.7", "203.0.113.8"],
        {"203.0.113.7"},
        [],
        "example.org",
        query_times=[100],
        target_times={100},
    )
    assert classified["route"] == "mixed"
    assert classified["direct"] is False
    assert classified["candidate_for_direct"] is False


def test_known_brand_alias_is_selectable_only_with_vpn_ipv4_evidence():
    classified = appliance._diagnostic_classify_resource(
        "jam.api.2gis.com",
        ["91.236.49.1"],
        set(),
        [],
        "2gis.ru",
        query_times=[100],
        target_times={100},
    )
    assert classified["category"] == "external_candidate"
    assert classified["candidate_for_direct"] is True


def test_diagnostic_result_accumulates_times_and_classifies_external_candidate(
    monkeypatch,
):
    token = "c" * 32
    session = {
        "domain": "example.org",
        "requested_client_ip": CLIENT,
        "resolved_client_ip": "",
        "started_at": time.time() - 30,
        "expires_at": time.time() - 1,
        "cursor": {"inode": 1, "offset": 0},
        "parser_state": {"transactions": {}, "selected_client_ip": CLIENT},
        "observed_resources": {},
    }
    monkeypatch.setitem(appliance.DIAGNOSTICS, token, session)
    monkeypatch.setattr(appliance, "_diagnostic_direct_ips", lambda: set())
    monkeypatch.setattr(appliance, "_diagnostic_domain_rules", lambda: [])

    target_lines = "\n".join(
        (
            query_line("200", "example.org", timestamp="Oct 19 23:05:44"),
            answer_line(
                "200",
                "reply",
                "example.org",
                "93.184.216.34",
                timestamp="Oct 19 23:05:44",
            ),
        )
    )
    external_lines = "\n".join(
        (
            query_line("201", "cdn.vendor.net", timestamp="Oct 19 23:05:48"),
            answer_line(
                "201",
                "reply",
                "cdn.vendor.net",
                "203.0.113.7",
                timestamp="Oct 19 23:05:48",
            ),
        )
    )
    deltas = iter(
        (
            (target_lines, {"inode": 1, "offset": 100}, False),
            (external_lines, {"inode": 1, "offset": 200}, False),
        )
    )
    monkeypatch.setattr(
        appliance, "_diagnostic_read_delta", lambda cursor: next(deltas)
    )

    appliance.diagnostic_result(token)
    result = appliance.diagnostic_result(token)
    by_host = {item["hostname"]: item for item in result["resources"]}
    external = by_host["cdn.vendor.net"]

    assert external["category"] == "external_candidate"
    assert external["candidate_eligible"] is False
    assert external["query_times"] == [83148]
    assert result["summary"]["target_site"] == 1
    assert result["summary"]["external_candidates"] == 1
    assert result["summary"]["background"] == 0


def test_classification_ui_displays_mixed_route_and_category_counts():
    root = Path(__file__).resolve().parents[3]
    html = (root / "appliance/maxvpn/index.html").read_text(encoding="utf-8")
    assert "x.route==='mixed'?'Смешанный'" in html
    assert "${s.external_candidates||0}" in html
    assert "${s.background||0}" in html
