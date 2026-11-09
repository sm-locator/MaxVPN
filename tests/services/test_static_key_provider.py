from backend.services.static_key_provider import StaticKeyProvider


def test_static_provider_returns_key_pair():
    provider = StaticKeyProvider()

    pair = provider.generate()

    assert pair.private_key == "private-key"
    assert pair.public_key == "public-key"
