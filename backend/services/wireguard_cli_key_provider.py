from __future__ import annotations

import subprocess

from backend.models.key_pair import KeyPair
from backend.ports.key_provider import KeyProvider


class WireGuardCLIKeyProvider(KeyProvider):
    """
    Generates WireGuard key pairs using the official wg utility.
    """

    def generate(self) -> KeyPair:
        private_key = subprocess.run(
            ["wg", "genkey"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        public_key = subprocess.run(
            ["wg", "pubkey"],
            input=private_key,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        return KeyPair(
            private_key=private_key,
            public_key=public_key,
        )
