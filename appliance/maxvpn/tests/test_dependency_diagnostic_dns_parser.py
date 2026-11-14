from pathlib import Path
from unittest.mock import patch

# The parser tests do not need appliance directories under /opt.
# Suppress directory creation only while importing the appliance module.
with patch.object(Path, "mkdir"):
    from appliance.maxvpn.server import _diagnostic_parse

CLIENT = "192.168.8.231"


def query_line(query_id, hostname, *, client=CLIENT, peer=None, pid="22762"):
    peer = peer or f"{client}/52360"
    return (
        f"Oct 19 23:05:44 dnsmasq[{pid}]: {query_id} {peer} "
        f"query[A] {hostname} from {client}"
    )


def answer_line(
    query_id, action, hostname, answer, *, peer=None, client=CLIENT, pid="22762"
):
    peer = peer or f"{client}/52360"
    return (
        f"Oct 19 23:05:44 dnsmasq[{pid}]: {query_id} {peer} "
        f"{action} {hostname} is {answer}"
    )


def test_regular_reply_a_record_is_correlated_by_transaction():
    query = query_line("120883", "jam.api.2gis.com")
    reply = answer_line("120883", "reply", "jam.api.2gis.com", "91.236.49.1")

    selected, resources = _diagnostic_parse(query + "\n" + reply, CLIENT)

    assert selected == CLIENT
    assert resources == [
        {
            "hostname": "jam.api.2gis.com",
            "ips": ["91.236.49.1"],
            "queries": 1,
            "query_times": [83144],
        }
    ]


def test_cached_a_answer_is_supported():
    query = query_line("120883", "jam.api.2gis.com")
    reply = answer_line("120883", "cached", "jam.api.2gis.com", "91.236.49.1")

    _, resources = _diagnostic_parse(query + "\n" + reply, CLIENT)

    item = next(
        resource for resource in resources if resource["hostname"] == "jam.api.2gis.com"
    )
    assert item["ips"] == ["91.236.49.1"]


def test_cached_cname_and_terminal_ipv4_attach_to_original_hostname():
    query = query_line("120884", "filekeeper-vod.2gis.com")
    cname = answer_line("120884", "cached", "filekeeper-vod.2gis.com", "<CNAME>")
    terminal = answer_line(
        "120884", "cached", "p28431.clients-cdnnow.ru", "185.253.21.13"
    )

    _, resources = _diagnostic_parse("\n".join((query, cname, terminal)), CLIENT)

    item = next(
        resource
        for resource in resources
        if resource["hostname"] == "filekeeper-vod.2gis.com"
    )
    assert item["ips"] == ["185.253.21.13"]
    assert item["queries"] == 1


def test_cname_transaction_survives_between_diagnostic_polls():
    state = {"transactions": {}, "selected_client_ip": CLIENT}
    query = query_line("120884", "filekeeper-vod.2gis.com")
    cname = answer_line("120884", "cached", "filekeeper-vod.2gis.com", "<CNAME>")

    _, first = _diagnostic_parse(query + "\n" + cname, CLIENT, parser_state=state)
    assert first[0]["hostname"] == "filekeeper-vod.2gis.com"
    assert first[0]["ips"] == []

    terminal = answer_line(
        "120884", "cached", "p28431.clients-cdnnow.ru", "185.253.21.13"
    )
    _, second = _diagnostic_parse(terminal, CLIENT, parser_state=state)
    item = next(
        resource
        for resource in second
        if resource["hostname"] == "filekeeper-vod.2gis.com"
    )
    assert item["ips"] == ["185.253.21.13"]


def test_transaction_reply_from_another_client_is_not_mixed_into_requested_client():
    other_client = "192.168.8.232"
    query_a = query_line(
        "120883", "jam.api.2gis.com", client=CLIENT, peer=CLIENT + "/52360"
    )
    query_b = query_line(
        "120884", "jam.api.2gis.com", client=other_client, peer=other_client + "/52361"
    )
    reply_b = answer_line(
        "120884",
        "reply",
        "jam.api.2gis.com",
        "91.236.49.99",
        client=other_client,
        peer=other_client + "/52361",
    )
    reply_a = answer_line(
        "120883",
        "reply",
        "jam.api.2gis.com",
        "91.236.49.1",
        client=CLIENT,
        peer=CLIENT + "/52360",
    )

    _, resources = _diagnostic_parse(
        "\n".join((query_a, query_b, reply_b, reply_a)), CLIENT
    )

    item = next(
        resource for resource in resources if resource["hostname"] == "jam.api.2gis.com"
    )
    assert item["ips"] == ["91.236.49.1"]
