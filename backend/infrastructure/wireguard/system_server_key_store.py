from __future__ import annotations

import os
from pathlib import Path

from backend.ports.wireguard_server_key_store import WireGuardServerKeyStore


class SystemWireGuardServerKeyStore(WireGuardServerKeyStore):
    """Stores the WireGuard server private key in the local filesystem."""

    def __init__(
        self,
        path: str = "/etc/maxvpn/wireguard/server_private.key",
    ) -> None:
        self._path = Path(path)

    def exists(self) -> bool:
        return self._path.is_file()

    def read(self) -> str:
        if not self.exists():
            raise RuntimeError(
                f"WireGuard server private key does not exist: {self._path}"
            )

        private_key = self._path.read_text(encoding="utf-8").strip()

        if not private_key:
            raise RuntimeError(f"WireGuard server private key is empty: {self._path}")

        return private_key

    def write(self, private_key: str) -> None:
        if not private_key.strip():
            raise ValueError("WireGuard server private key cannot be empty.")

        self._path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._path.write_text(
            private_key.strip() + "\n",
            encoding="utf-8",
        )

        os.chmod(self._path, 0o600)
