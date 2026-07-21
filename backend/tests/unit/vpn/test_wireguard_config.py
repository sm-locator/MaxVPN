from app.vpn.models import WireGuardClientConfig
from app.vpn.wireguard.config import WireGuardConfigGenerator


def test_generate_client_config() -> None:
    config = WireGuardClientConfig(
        private_key="private_key",
        client_ip="10.0.0.2",
        dns="1.1.1.1",
        server_public_key="server_public_key",
        endpoint="vpn.example.com:51820",
    )

    result = WireGuardConfigGenerator().generate(config)

    assert "PrivateKey = private_key" in result
    assert "Address = 10.0.0.2/32" in result
    assert "DNS = 1.1.1.1" in result
    assert "PublicKey = server_public_key" in result
    assert "Endpoint = vpn.example.com:51820" in result
