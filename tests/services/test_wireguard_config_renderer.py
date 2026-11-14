from backend.services.wireguard_config_renderer import (
    WireGuardConfigRenderer,
)
from tests.factories import make_client_config


def test_renderer_generates_wireguard_config():
    renderer = WireGuardConfigRenderer()

    config = make_client_config()

    text = renderer.render(config)

    assert "[Interface]" in text
    assert "PrivateKey = private-key" in text
    assert "Address = 10.100.0.2/32" in text
    assert "DNS = 1.1.1.1" in text
    assert "MTU = 1420" in text

    assert "[Peer]" in text
    assert "PublicKey = server-public-key" in text
    assert f"Endpoint = {config.server.endpoint}" in text
    assert "AllowedIPs = 0.0.0.0/0" in text
    assert "PersistentKeepalive = 25" in text
