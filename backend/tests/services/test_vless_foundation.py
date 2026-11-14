from __future__ import annotations

import json

import pytest
from backend.models.vless_config import VlessRealityConfig
from backend.services.vless_profile_importer import VlessProfileImporter
from backend.services.vless_singbox_config_renderer import (
    VlessSingBoxConfigRenderer,
)

TEST_UUID = "00000000-0000-0000-0000-000000000000"
TEST_PUBLIC_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

REALITY_LINK = (
    f"vless://{TEST_UUID}@nl2.example.com:443"
    "?encryption=none"
    "&flow=xtls-rprx-vision"
    "&type=tcp"
    "&security=reality"
    "&sni=nl2.example.com"
    "&fp=firefox"
    f"&pbk={TEST_PUBLIC_KEY}"
    "&sid=41ae8e266bc3346f"
    "#Test%20profile"
)


def test_import_reality_vless_uri() -> None:
    result = VlessProfileImporter().parse(REALITY_LINK)

    assert result.name == "Test profile"
    assert result.address == "nl2.example.com"
    assert result.port == 443
    assert result.uuid == TEST_UUID
    assert result.flow == "xtls-rprx-vision"
    assert result.network == "tcp"
    assert result.reality == VlessRealityConfig(
        public_key=TEST_PUBLIC_KEY,
        server_name="nl2.example.com",
        short_id="41ae8e266bc3346f",
        fingerprint="firefox",
    )


def test_importer_rejects_non_tcp_uri() -> None:
    link = REALITY_LINK.replace("type=tcp", "type=ws")

    with pytest.raises(ValueError, match="Unsupported VLESS network"):
        VlessProfileImporter().parse(link)


def test_importer_rejects_unimplemented_tls_uri() -> None:
    link = f"vless://{TEST_UUID}@nl2.example.com:443?security=tls&sni=nl2.example.com"

    with pytest.raises(ValueError, match="Unsupported VLESS security"):
        VlessProfileImporter().parse(link)


def test_importer_still_accepts_xray_json() -> None:
    document = {
        "remarks": "JSON profile",
        "outbounds": [
            {
                "protocol": "vless",
                "tag": "proxy",
                "settings": {
                    "vnext": [
                        {
                            "address": "nl2.example.com",
                            "port": 443,
                            "users": [
                                {
                                    "id": TEST_UUID,
                                    "flow": "xtls-rprx-vision",
                                }
                            ],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "publicKey": TEST_PUBLIC_KEY,
                        "serverName": "nl2.example.com",
                        "shortId": "41ae8e266bc3346f",
                        "fingerprint": "firefox",
                    },
                },
            }
        ],
    }

    result = VlessProfileImporter().parse(json.dumps(document))

    assert result.name == "JSON profile"
    assert result.address == "nl2.example.com"
    assert result.reality is not None
    assert result.reality.public_key == TEST_PUBLIC_KEY


def test_render_complete_tun_config() -> None:
    server = VlessProfileImporter().parse(REALITY_LINK)

    config = VlessSingBoxConfigRenderer().render(server)

    assert config["inbounds"] == [
        {
            "type": "tun",
            "tag": "maxvpn-tun-in",
            "interface_name": "maxvpn0",
            "address": ["172.19.0.1/30"],
            "mtu": 1380,
            "auto_route": False,
        }
    ]

    assert config["outbounds"][0]["type"] == "vless"
    # The imported VLESS URI type=tcp describes its transport and must not be
    # copied into sing-box's outbound network restriction (which would disable
    # UDP destination traffic in TUN mode).
    assert "network" not in config["outbounds"][0]
    assert config["outbounds"][0]["packet_encoding"] == "xudp"
    assert config["outbounds"][0]["flow"] == "xtls-rprx-vision"
    assert config["outbounds"][0]["tls"]["reality"]["enabled"] is True
    assert config["route"]["final"] == "vless-out"
    assert config["route"]["default_domain_resolver"] == "endpoint-dns"
    assert config["route"]["auto_detect_interface"] is True

    assert config["outbounds"][0]["domain_resolver"] == "endpoint-dns"
    assert config["dns"]["final"] == "vless-doh"
    dns_servers = {item["tag"]: item for item in config["dns"]["servers"]}
    assert dns_servers["vless-doh"]["type"] == "https"
    assert dns_servers["vless-doh"]["detour"] == "vless-out"
    assert dns_servers["vless-doh"]["server"] == "1.1.1.1"
    assert "detour" not in dns_servers["endpoint-dns"]
    assert dns_servers["endpoint-dns"]["routing_mark"] == 100
    assert config["route"]["rules"] == [{"port": 53, "action": "hijack-dns"}]

    # Ensure the complete config is serializable as sing-box JSON.
    json.dumps(config)


def test_renderer_rejects_invalid_tun_parameters() -> None:
    server = VlessProfileImporter().parse(REALITY_LINK)
    renderer = VlessSingBoxConfigRenderer()

    with pytest.raises(ValueError, match="interface name"):
        renderer.render(server, interface_name="interface-name-too-long")

    with pytest.raises(ValueError, match="MTU"):
        renderer.render(server, mtu=10000)


def test_render_multi_profile_urltest_selector_config() -> None:
    server = VlessProfileImporter().parse(REALITY_LINK)
    config = VlessSingBoxConfigRenderer().render_profiles([(1, server), (2, server)])

    outbounds = {item["tag"]: item for item in config["outbounds"]}
    assert outbounds["vless-profile-1"]["type"] == "vless"
    assert outbounds["vless-profile-2"]["type"] == "vless"
    for tag in ("vless-profile-1", "vless-profile-2"):
        assert "network" not in outbounds[tag]
        assert outbounds[tag]["packet_encoding"] == "xudp"
    assert outbounds["vless-auto"]["type"] == "urltest"
    assert outbounds["vless-auto"]["outbounds"] == [
        "vless-profile-1",
        "vless-profile-2",
    ]
    assert outbounds["vless-auto"]["interval"] == "3m"
    assert outbounds["vless-auto"]["url"] == "https://cp.cloudflare.com/generate_204"
    assert outbounds["vless-auto"]["tolerance"] == 50
    assert outbounds["vless-out"]["type"] == "selector"
    assert outbounds["vless-out"]["default"] == "vless-auto"
    assert config["inbounds"][0]["interface_name"] == "maxvpn0"
    assert config["inbounds"][0]["auto_route"] is False
    assert config["route"]["final"] == "vless-out"
    assert (
        config["experimental"]["clash_api"]["external_controller"] == "127.0.0.1:9090"
    )
