from ipaddress import IPv4Address

from app.vpn.models import WireGuardClient


def test_update_changes_client_fields() -> None:
    client = WireGuardClient(
        name="phone",
        private_key="private_key",
        public_key="public_key",
        ip_address=IPv4Address("10.8.0.2"),
    )

    client.update(
        name="iphone",
        description="My iPhone",
        enabled=False,
    )

    assert client.name == "iphone"
    assert client.description == "My iPhone"
    assert client.enabled is False
