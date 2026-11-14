from backend.services.amneziawg_runtime_config import (
    AmneziaWGRuntimeConfigGenerator,
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


def test_runtime_generator_produces_awg_compatible_config():
    result = AmneziaWGRuntimeConfigGenerator().generate(PROVIDER_CONFIG)

    text = result.text

    assert "[Interface]" in text
    assert "[Peer]" in text

    assert "PrivateKey = private-key" in text

    assert "Address =" not in text
    assert "DNS =" not in text
    assert "MTU =" not in text

    assert "Jc = 5" in text
    assert "Jmin = 49" in text
    assert "Jmax = 998" in text

    assert "S1 = 17" in text
    assert "S2 = 110" in text
    assert "S3 = 1" in text
    assert "S4 = 2" in text

    assert "H1 = 1597513488-1927637527" in text
    assert "H4 = 2143034152-2146422435" in text

    assert "I1 = <r 2><b 0x858000010001" in text
    assert "I5 = 0" in text

    assert "PublicKey = server-public-key" in text
    assert "PresharedKey = psk" in text
    assert "AllowedIPs = 0.0.0.0/0" in text
    assert "Endpoint = 194.26.192.36:39743" in text
    assert "PersistentKeepalive = 25" in text


def test_runtime_generator_does_not_modify_provider_text():
    original = PROVIDER_CONFIG

    AmneziaWGRuntimeConfigGenerator().generate(original)

    assert original == PROVIDER_CONFIG
