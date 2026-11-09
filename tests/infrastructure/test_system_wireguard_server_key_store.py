from pathlib import Path

import pytest

from backend.infrastructure.wireguard.system_server_key_store import (
    SystemWireGuardServerKeyStore,
)


def test_key_store_reports_missing_key(tmp_path: Path):
    path = tmp_path / "server_private.key"

    store = SystemWireGuardServerKeyStore(str(path))

    assert store.exists() is False

    with pytest.raises(RuntimeError, match="does not exist"):
        store.read()


def test_key_store_writes_and_reads_private_key(tmp_path: Path):
    path = tmp_path / "server_private.key"
    private_key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

    store = SystemWireGuardServerKeyStore(str(path))

    store.write(private_key)

    assert store.exists() is True
    assert store.read() == private_key


def test_key_store_sets_private_key_permissions(tmp_path: Path):
    path = tmp_path / "server_private.key"
    private_key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

    store = SystemWireGuardServerKeyStore(str(path))

    store.write(private_key)

    assert path.stat().st_mode & 0o777 == 0o600


def test_key_store_rejects_empty_private_key(tmp_path: Path):
    path = tmp_path / "server_private.key"

    store = SystemWireGuardServerKeyStore(str(path))

    with pytest.raises(ValueError, match="cannot be empty"):
        store.write("   ")
