from backend.models.client_config import ClientConfig
from backend.models.key_pair import KeyPair
from backend.models.peer import Peer
from backend.models.tunnel import Tunnel
from tests.factories import make_server


def make_client_config() -> ClientConfig:
    return ClientConfig(
        server=make_server(),
        key_pair=KeyPair(
            private_key="private",
            public_key="public",
        ),
        tunnel=Tunnel(
            address="10.0.0.2/32",
        ),
        peer=Peer(
            public_key="server-public-key",
            allowed_ips="0.0.0.0/0",
        ),
    )


def test_client_config_contains_server():
    config = make_client_config()

    assert config.server.id == 1


def test_client_config_contains_key_pair():
    config = make_client_config()

    assert config.key_pair.private_key == "private"


def test_client_config_contains_tunnel():
    config = make_client_config()

    assert config.tunnel.address == "10.0.0.2/32"


def test_client_config_contains_peer():
    config = make_client_config()

    assert config.peer.public_key == "server-public-key"
