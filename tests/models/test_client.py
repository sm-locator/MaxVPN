from backend.models.client import Client


def test_client_has_expected_defaults():
    client = Client(
        id=None,
        name="phone",
        server_id=1,
        private_key="private-key",
        public_key="public-key",
        address="10.100.0.2/32",
    )

    assert client.id is None
    assert client.name == "phone"
    assert client.server_id == 1
    assert client.enabled is True
    assert client.description is None
