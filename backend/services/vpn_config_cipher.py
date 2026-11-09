from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class VPNConfigCipher:
    """Encrypts and decrypts persisted VPN configuration."""

    def __init__(self, key: str) -> None:
        if not key:
            raise ValueError("encryption key must not be empty")

        try:
            self._fernet = Fernet(key.encode("utf-8"))
        except Exception as exc:
            raise ValueError("invalid Fernet encryption key") from exc

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            raise ValueError("plaintext must not be empty")

        return self._fernet.encrypt(
            plaintext.encode("utf-8"),
        ).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext:
            raise ValueError("ciphertext must not be empty")

        try:
            return self._fernet.decrypt(
                ciphertext.encode("utf-8"),
            ).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("invalid encrypted VPN configuration") from exc
