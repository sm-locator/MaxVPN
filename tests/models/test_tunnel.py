from backend.models.tunnel import Tunnel


def test_tunnel_has_address():
    tunnel = Tunnel(address="10.0.0.2/32")

    assert tunnel.address == "10.0.0.2/32"


def test_tunnel_default_dns():
    tunnel = Tunnel(address="10.0.0.2/32")

    assert tunnel.dns == "1.1.1.1"


def test_tunnel_default_mtu():
    tunnel = Tunnel(address="10.0.0.2/32")

    assert tunnel.mtu == 1420


def test_tunnel_custom_values():
    tunnel = Tunnel(
        address="10.0.0.2/32",
        dns="8.8.8.8",
        mtu=1380,
    )

    assert tunnel.dns == "8.8.8.8"
    assert tunnel.mtu == 1380
