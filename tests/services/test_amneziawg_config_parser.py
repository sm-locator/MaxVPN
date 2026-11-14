import pytest

from backend.models.amneziawg_config import AmneziaWGConfig
from backend.services.amneziawg_config_parser import (
    AmneziaWGConfigError,
    AmneziaWGConfigParser,
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


def test_parser_reads_full_provider_profile():
    config = AmneziaWGConfigParser().parse(PROVIDER_CONFIG)

    assert isinstance(config, AmneziaWGConfig)

    interface = config.interface
    assert interface.address == "10.9.9.200/32"
    assert interface.mtu == 1380
    assert interface.dns == "1.1.1.1"

    assert interface.jc == 5
    assert interface.jmin == 49
    assert interface.jmax == 998

    assert interface.s1 == 17
    assert interface.s2 == 110
    assert interface.s3 == 1
    assert interface.s4 == 2

    assert interface.h1 == "1597513488-1927637527"
    assert interface.h2 == "1959162374-2134706886"
    assert interface.h3 == "2135520142-2141053315"
    assert interface.h4 == "2143034152-2146422435"

    assert interface.i1.startswith("<r 2><b 0x")
    assert interface.i2 == "0"
    assert interface.i3 == "0"
    assert interface.i4 == "0"
    assert interface.i5 == "0"

    peer = config.peer
    assert peer.public_key == "server-public-key"
    assert peer.allowed_ips == ("0.0.0.0/0",)
    assert peer.endpoint == "194.26.192.36:39743"
    assert peer.persistent_keepalive == 25
    assert peer.preshared_key == "psk"


def test_parser_preserves_multiple_allowed_ips():
    text = PROVIDER_CONFIG.replace(
        "AllowedIPs = 0.0.0.0/0",
        "AllowedIPs = 0.0.0.0/0\nAllowedIPs = ::/0",
    )

    config = AmneziaWGConfigParser().parse(text)

    assert config.peer.allowed_ips == ("0.0.0.0/0", "::/0")


def test_parser_rejects_unknown_interface_key():
    text = PROVIDER_CONFIG.replace(
        "Jc = 5",
        "UnknownThing = 123\nJc = 5",
    )

    with pytest.raises(AmneziaWGConfigError, match="Unsupported key"):
        AmneziaWGConfigParser().parse(text)


def test_parser_rejects_duplicate_scalar_key():
    text = PROVIDER_CONFIG.replace(
        "Jc = 5",
        "Jc = 5\nJc = 6",
    )

    with pytest.raises(AmneziaWGConfigError, match="Duplicate key"):
        AmneziaWGConfigParser().parse(text)


def test_parser_rejects_empty_required_private_key():
    text = PROVIDER_CONFIG.replace(
        "PrivateKey = private-key",
        "PrivateKey =",
    )

    with pytest.raises(
        AmneziaWGConfigError,
        match="Missing required key: PrivateKey",
    ):
        AmneziaWGConfigParser().parse(text)


def test_parser_rejects_empty_required_address():
    text = PROVIDER_CONFIG.replace(
        "Address = 10.9.9.200/32",
        "Address =",
    )

    with pytest.raises(
        AmneziaWGConfigError,
        match="Missing required key: Address",
    ):
        AmneziaWGConfigParser().parse(text)


def test_parser_rejects_empty_required_public_key():
    text = PROVIDER_CONFIG.replace(
        "PublicKey = server-public-key",
        "PublicKey =",
    )

    with pytest.raises(
        AmneziaWGConfigError,
        match="Missing required key: PublicKey",
    ):
        AmneziaWGConfigParser().parse(text)


def test_parser_rejects_empty_required_endpoint():
    text = PROVIDER_CONFIG.replace(
        "Endpoint = 194.26.192.36:39743",
        "Endpoint =",
    )

    with pytest.raises(
        AmneziaWGConfigError,
        match="Missing required key: Endpoint",
    ):
        AmneziaWGConfigParser().parse(text)


def test_parse_allowed_ips_comma_separated() -> None:
    from backend.services.amneziawg_config_parser import (
        AmneziaWGConfigParser,
    )

    config = AmneziaWGConfigParser().parse("""[Interface]
PrivateKey = interface-private
Address = 10.8.0.26/24
MTU = 1380
Jc = 5
Jmin = 2
Jmax = 9
S1 = 0
S2 = 0
H1 = 1
H2 = 2
H3 = 3
H4 = 4

[Peer]
PublicKey = peer-public
PresharedKey = peer-preshared
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = 109.172.55.99:51820
PersistentKeepalive = 25
""")

    assert config.peer.allowed_ips == (
        "0.0.0.0/0",
        "::/0",
    )
