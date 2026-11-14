from __future__ import annotations

import json

import pytest

from backend.models.vless_config import (
    VlessRealityConfig,
    VlessServerConfig,
)
from backend.services.vless_config_parser import VlessConfigParser
from backend.services.vless_singbox_renderer import VlessSingBoxRenderer

SAMPLE = {
    "remarks": "🇳🇱 Нидерланды",
    "outbounds": [
        {
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": "nl2.japancase.site",
                        "port": 443,
                        "users": [
                            {
                                "encryption": "none",
                                "flow": "xtls-rprx-vision",
                                "id": "00000000-0000-0000-0000-000000000000",
                                "level": 8,
                                "security": "auto",
                            }
                        ],
                    }
                ]
            },
            "streamSettings": {
                "network": "tcp",
                "realitySettings": {
                    "fingerprint": "firefox",
                    "publicKey": "public-key",
                    "serverName": "nl2.japancase.site",
                    "shortId": "41ae8e266bc3346f",
                    "show": False,
                    "spiderX": "/",
                },
                "security": "reality",
                "tcpSettings": {
                    "header": {
                        "type": "none",
                    },
                },
            },
            "tag": "proxy",
        },
    ],
}


def test_parse_happ_xray_vless_reality() -> None:
    result = VlessConfigParser().parse(json.dumps(SAMPLE))

    assert result == VlessServerConfig(
        name="🇳🇱 Нидерланды",
        address="nl2.japancase.site",
        port=443,
        uuid="00000000-0000-0000-0000-000000000000",
        flow="xtls-rprx-vision",
        network="tcp",
        reality=VlessRealityConfig(
            public_key="public-key",
            server_name="nl2.japancase.site",
            short_id="41ae8e266bc3346f",
            fingerprint="firefox",
        ),
    )


def test_parse_requires_vless_outbound() -> None:
    with pytest.raises(ValueError, match="No VLESS outbound found"):
        VlessConfigParser().parse({"outbounds": [{"protocol": "freedom"}]})


def test_parse_rejects_multiple_vless_outbounds() -> None:
    sample = json.loads(json.dumps(SAMPLE))
    sample["outbounds"] = [
        dict(SAMPLE["outbounds"][0]),
        dict(SAMPLE["outbounds"][0]),
    ]

    with pytest.raises(ValueError, match="Multiple VLESS outbounds"):
        VlessConfigParser().parse(sample)


def test_parse_rejects_invalid_port() -> None:
    sample = json.loads(json.dumps(SAMPLE))
    sample["outbounds"][0]["settings"]["vnext"][0]["port"] = 70000

    with pytest.raises(ValueError, match="between 1 and 65535"):
        VlessConfigParser().parse(sample)


def test_render_to_sing_box_vless_reality() -> None:
    config = VlessConfigParser().parse(SAMPLE)

    outbound = VlessSingBoxRenderer().render_outbound(
        config,
        tag="vless-nl-01",
    )

    assert outbound == {
        "type": "vless",
        "tag": "vless-nl-01",
        "server": "nl2.japancase.site",
        "server_port": 443,
        "uuid": "00000000-0000-0000-0000-000000000000",
        "packet_encoding": "xudp",
        "flow": "xtls-rprx-vision",
        "tls": {
            "enabled": True,
            "server_name": "nl2.japancase.site",
            "reality": {
                "enabled": True,
                "public_key": "public-key",
                "short_id": "41ae8e266bc3346f",
            },
            "utls": {
                "enabled": True,
                "fingerprint": "firefox",
            },
        },
    }
