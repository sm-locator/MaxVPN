from __future__ import annotations

from backend.models.key_pair import KeyPair
from backend.ports.key_provider import KeyProvider


class StaticKeyProvider(KeyProvider):
    """
    Test implementation returning predefined keys.
    """

    def generate(self) -> KeyPair:
        return KeyPair(
            private_key="private-key",
            public_key="public-key",
        )
