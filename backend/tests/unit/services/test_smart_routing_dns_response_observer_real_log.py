from backend.services.smart_routing_dns_response_observer import (
    SmartRoutingDnsResponseObserver,
)


def test_parse_real_dnsmasq_maxvpn_response():
    output = (
        "Sep 12 00:05:09 dnsmasq[762]: "
        "12 127.0.0.1/33736 query[A] "
        "maxvpn-test.gps.navy from 127.0.0.1\n"
        "Sep 12 00:05:09 dnsmasq[762]: "
        "12 127.0.0.1/33736 ipset add MAXVPN_DIRECT "
        "81.90.181.120 maxvpn-test.gps.navy\n"
        "Sep 12 00:05:09 dnsmasq[762]: "
        "12 127.0.0.1/33736 reply "
        "maxvpn-test.gps.navy is 81.90.181.120\n"
    )

    result = SmartRoutingDnsResponseObserver._parse_responses(
        output,
        {"gps.navy"},
    )

    assert len(result) == 1
    assert result[0].transaction_id == "12"
    assert result[0].domain == "maxvpn-test.gps.navy"
    assert result[0].ipv4_addresses == ("81.90.181.120",)


def test_parse_real_cname_chain():
    output = (
        "Sep 12 00:04:51 dnsmasq[762]: "
        "4 192.168.8.231/34610 query[A] "
        "main.vscode-cdn.net from 192.168.8.231\n"
        "Sep 12 00:04:51 dnsmasq[762]: "
        "4 192.168.8.231/34610 reply "
        "main.vscode-cdn.net is <CNAME>\n"
        "Sep 12 00:04:51 dnsmasq[762]: "
        "4 192.168.8.231/34610 reply "
        "vscode-cdn.z01.azurefd.net is <CNAME>\n"
        "Sep 12 00:04:51 dnsmasq[762]: "
        "4 192.168.8.231/34610 reply "
        "mr-z01.tm-azurefd.net is 150.171.109.53\n"
    )

    result = SmartRoutingDnsResponseObserver._parse_responses(
        output,
        {"vscode-cdn.net"},
    )

    assert len(result) == 1
    assert result[0].domain == "main.vscode-cdn.net"
    assert result[0].ipv4_addresses == ("150.171.109.53",)


def test_parse_real_cian_response():
    output = (
        "Sep 12 00:05:09 dnsmasq[762]: "
        "14 127.0.0.1/59636 query[A] "
        "cian.ru from 127.0.0.1\n"
        "Sep 12 00:05:14 dnsmasq[762]: "
        "14 127.0.0.1/59636 ipset add MAXVPN_DIRECT "
        "51.250.123.126 cian.ru\n"
        "Sep 12 00:05:14 dnsmasq[762]: "
        "14 127.0.0.1/59636 reply "
        "cian.ru is 51.250.123.126\n"
    )

    result = SmartRoutingDnsResponseObserver._parse_responses(
        output,
        {"cian.ru"},
    )

    assert len(result) == 1
    assert result[0].ipv4_addresses == ("51.250.123.126",)
