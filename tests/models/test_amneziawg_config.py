from backend.models.amneziawg_config import (
    AmneziaWGConfig,
    AmneziaWGInterface,
    AmneziaWGPeer,
)


def test_amneziawg_interface_preserves_extended_parameters():
    interface = AmneziaWGInterface(
        private_key="private-key",
        address="10.9.9.200/32",
        mtu=1380,
        dns="1.1.1.1",
        jc=5,
        jmin=49,
        jmax=998,
        s1=17,
        s2=110,
        s3=1,
        s4=2,
        h1="1597513488-1927637527",
        h2="1959162374-2134706886",
        h3="2135520142-2141053315",
        h4="2143034152-2146422435",
        i1="<r 2><b 0x85800001>",
        i2="0",
        i3="0",
        i4="0",
        i5="0",
    )

    assert interface.jc == 5
    assert interface.jmin == 49
    assert interface.jmax == 998

    assert interface.s3 == 1
    assert interface.s4 == 2

    assert interface.h1 == "1597513488-1927637527"
    assert interface.i1 == "<r 2><b 0x85800001>"


def test_amneziawg_peer_preserves_multiple_allowed_ips():
    peer = AmneziaWGPeer(
        public_key="server-public-key",
        allowed_ips=("0.0.0.0/0", "::/0"),
        endpoint="194.26.192.36:39743",
        persistent_keepalive=25,
        preshared_key="psk",
    )

    assert peer.allowed_ips == ("0.0.0.0/0", "::/0")
    assert peer.endpoint == "194.26.192.36:39743"


def test_amneziawg_config_is_composed_of_interface_and_peer():
    interface = AmneziaWGInterface(
        private_key="private-key",
        address="10.9.9.200/32",
    )
    peer = AmneziaWGPeer(
        public_key="server-public-key",
        allowed_ips=("0.0.0.0/0",),
        endpoint="194.26.192.36:39743",
    )

    config = AmneziaWGConfig(
        interface=interface,
        peer=peer,
    )

    assert config.interface is interface
    assert config.peer is peer
