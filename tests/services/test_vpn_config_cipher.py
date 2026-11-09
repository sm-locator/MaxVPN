from cryptography.fernet import Fernet
import pytest

from backend.services.vpn_config_cipher import VPNConfigCipher


def make_cipher() -> VPNConfigCipher:
    key = Fernet.generate_key().decode("utf-8")
    return VPNConfigCipher(key)


def test_encrypt_decrypt_round_trip() -> None:
    cipher = make_cipher()

    plaintext = "[Interface]\nPrivateKey = test-secret\n"

    encrypted = cipher.encrypt(plaintext)

    assert encrypted != plaintext
    assert cipher.decrypt(encrypted) == plaintext


def test_encryption_is_not_plaintext() -> None:
    cipher = make_cipher()

    plaintext = "PrivateKey = test-secret"

    encrypted = cipher.encrypt(plaintext)

    assert plaintext not in encrypted


def test_empty_plaintext_is_rejected() -> None:
    cipher = make_cipher()

    with pytest.raises(
        ValueError,
        match="plaintext must not be empty",
    ):
        cipher.encrypt("")


def test_empty_ciphertext_is_rejected() -> None:
    cipher = make_cipher()

    with pytest.raises(
        ValueError,
        match="ciphertext must not be empty",
    ):
        cipher.decrypt("")


def test_wrong_key_cannot_decrypt() -> None:
    first = make_cipher()
    second = make_cipher()

    encrypted = first.encrypt("secret")

    with pytest.raises(
        ValueError,
        match="invalid encrypted VPN configuration",
    ):
        second.decrypt(encrypted)


def test_tampered_ciphertext_is_rejected() -> None:
    cipher = make_cipher()

    encrypted = cipher.encrypt("secret")
    tampered = encrypted[:-1] + ("A" if encrypted[-1] != "A" else "B")

    with pytest.raises(
        ValueError,
        match="invalid encrypted VPN configuration",
    ):
        cipher.decrypt(tampered)


def test_invalid_key_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="invalid Fernet encryption key",
    ):
        VPNConfigCipher("invalid-key")
