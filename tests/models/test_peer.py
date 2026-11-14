from backend.models.peer import Peer


def test_peer_has_public_key():
    peer = Peer(
        public_key="abc",
        allowed_ips="0.0.0.0/0",
    )

    assert peer.public_key == "abc"


def test_peer_has_allowed_ips():
    peer = Peer(
        public_key="abc",
        allowed_ips="10.0.0.2/32",
    )

    assert peer.allowed_ips == "10.0.0.2/32"


def test_peer_default_keepalive():
    peer = Peer(
        public_key="abc",
        allowed_ips="0.0.0.0/0",
    )

    assert peer.persistent_keepalive == 25


def test_peer_custom_keepalive():
    peer = Peer(
        public_key="abc",
        allowed_ips="0.0.0.0/0",
        persistent_keepalive=15,
    )

    assert peer.persistent_keepalive == 15
