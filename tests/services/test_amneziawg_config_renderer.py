from backend.services.amneziawg_config_parser import (
    AmneziaWGConfigParser,
)
from backend.services.amneziawg_config_renderer import (
    AmneziaWGConfigRenderer,
)

PROVIDER_CONFIG = """\
[Interface]
PrivateKey = private-key
Address = 10.9.9.200/32
DNS = 1.1.1.1
MTU = 1380
Jc = 5
Jmin = 49
Jmax = 998
S1 = 17
S2 = 110
S3 = 1
S4 = 2
H1 = 1597513488-1927637527
H2 = 1959162374-2134706886
H3 = 2135520142-2141053315
H4 = 2143034152-2146422435
I1 = <r 2><b 0x858000010001000000000669636c6f756403636f6d0000010001c00c000100010000105a00044d583737>
I2 = 0
I3 = 0
I4 = 0
I5 = 0

[Peer]
PublicKey = server-public-key
AllowedIPs = 0.0.0.0/0
Endpoint = 194.26.192.36:39743
PersistentKeepalive = 25
PresharedKey = psk
"""


def test_full_renderer_preserves_provider_fields():
    config = AmneziaWGConfigParser().parse(PROVIDER_CONFIG)

    text = AmneziaWGConfigRenderer().render_full(config)

    assert "Address = 10.9.9.200/32" in text
    assert "DNS = 1.1.1.1" in text
    assert "MTU = 1380" in text

    assert "S3 = 1" in text
    assert "S4 = 2" in text
    assert "I1 = <r 2><b 0x858000010001" in text

    assert "Endpoint = 194.26.192.36:39743" in text


def test_awg_runtime_renderer_excludes_openwrt_fields():
    config = AmneziaWGConfigParser().parse(PROVIDER_CONFIG)

    text = AmneziaWGConfigRenderer().render_awg_runtime(config)

    assert "Address =" not in text
    assert "DNS =" not in text
    assert "MTU =" not in text

    assert "Jc = 5" in text
    assert "S3 = 1" in text
    assert "S4 = 2" in text
    assert "H1 = 1597513488-1927637527" in text
    assert "I1 = <r 2><b 0x858000010001" in text


def test_runtime_renderer_round_trip_preserves_awg_values():
    parser = AmneziaWGConfigParser()
    renderer = AmneziaWGConfigRenderer()

    original = parser.parse(PROVIDER_CONFIG)
    runtime_text = renderer.render_awg_runtime(original)

    reparsed = parser.parse(
        runtime_text.replace(
            "[Interface]\n",
            "[Interface]\nAddress = 10.9.9.200/32\n",
            1,
        )
    )

    assert reparsed.interface.private_key == original.interface.private_key
    assert reparsed.interface.address == original.interface.address

    assert reparsed.interface.jc == original.interface.jc
    assert reparsed.interface.jmin == original.interface.jmin
    assert reparsed.interface.jmax == original.interface.jmax

    assert reparsed.interface.s1 == original.interface.s1
    assert reparsed.interface.s2 == original.interface.s2
    assert reparsed.interface.s3 == original.interface.s3
    assert reparsed.interface.s4 == original.interface.s4

    assert reparsed.interface.h1 == original.interface.h1
    assert reparsed.interface.h2 == original.interface.h2
    assert reparsed.interface.h3 == original.interface.h3
    assert reparsed.interface.h4 == original.interface.h4

    assert reparsed.interface.i1 == original.interface.i1
    assert reparsed.interface.i2 == original.interface.i2
    assert reparsed.interface.i3 == original.interface.i3
    assert reparsed.interface.i4 == original.interface.i4
    assert reparsed.interface.i5 == original.interface.i5

    assert reparsed.peer.public_key == original.peer.public_key
    assert reparsed.peer.endpoint == original.peer.endpoint
    assert reparsed.peer.allowed_ips == original.peer.allowed_ips
    assert reparsed.peer.persistent_keepalive == original.peer.persistent_keepalive
    assert reparsed.peer.preshared_key == original.peer.preshared_key
