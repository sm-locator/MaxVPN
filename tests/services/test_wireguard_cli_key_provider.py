from backend.services.wireguard_cli_key_provider import (
    WireGuardCLIKeyProvider,
)


def test_generate_real_wireguard_keypair():
    provider = WireGuardCLIKeyProvider()

    pair = provider.generate()

    assert pair.private_key
    assert pair.public_key

    assert len(pair.private_key) > 40
    assert len(pair.public_key) > 40

    assert pair.private_key != pair.public_key
