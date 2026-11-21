import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[3]
SNAPSHOT_SOURCE = REPO / "scripts" / "brume3_pr6" / "router_snapshot.py"
SCRIPT_WRAPPER = REPO / "scripts" / "brume3_pr6" / "run.sh"
CAPTURE = REPO / "scripts" / "brume3_pr6" / "capture-live-code.sh"
VLESS_STOP = (
    REPO / "appliance" / "maxvpn" / "compat" / "brume3-vless-stop-guarded.sh"
)

spec = importlib.util.spec_from_file_location("maxvpn_brume3_pr6_snapshot", SNAPSHOT_SOURCE)
snapshot = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = snapshot
spec.loader.exec_module(snapshot)


@pytest.fixture
def private_fixture(tmp_path, monkeypatch):
    backup_dir = tmp_path / "private"
    program = tmp_path / "program.py"
    program.write_text("before\n", encoding="utf-8")
    os.chmod(program, 0o640)
    secret = tmp_path / "profiles.json"
    secret.write_text('{"secret":"private-test-value"}\n', encoding="utf-8")
    os.chmod(secret, 0o600)
    absent = tmp_path / "missing-helper"
    monkeypatch.setattr(snapshot, "BASE", backup_dir)
    monkeypatch.setattr(
        snapshot, "TARGETS", (str(program), str(secret), str(absent))
    )
    monkeypatch.setattr(snapshot, "RESTORABLE", frozenset((str(program), str(absent))))
    monkeypatch.setattr(snapshot.os, "geteuid", lambda: 0)
    return program, secret, absent, backup_dir


def _backup_id(base):
    matches = list(base.glob("pr6-*"))
    assert len(matches) == 1
    return matches[0].name


def test_private_backup_verify_and_no_secret_stdout(private_fixture, capsys):
    program, secret, absent, base = private_fixture
    assert snapshot.backup() == 0
    output = capsys.readouterr().out
    assert "BACKUP_VERIFIED=YES" in output
    assert "private-test-value" not in output
    backup_id = _backup_id(base)
    assert snapshot.verify(backup_id)["backup_id"] == backup_id
    assert os.stat(base).st_mode & 0o077 == 0
    assert os.stat(base / backup_id).st_mode & 0o077 == 0
    assert not absent.exists()


def test_modified_backup_blob_is_rejected(private_fixture):
    _, _, _, base = private_fixture
    snapshot.backup()
    ident = _backup_id(base)
    (base / ident / "000.blob").write_text("tampered\n")
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        snapshot.verify(ident)


def test_restore_requires_approved_deployment_receipt(private_fixture):
    _, _, _, base = private_fixture
    snapshot.backup()
    ident = _backup_id(base)
    with pytest.raises(RuntimeError, match="receipt"):
        snapshot.restore(ident, "RESTORE-" + ident)


def test_restore_rejects_unknown_live_file_even_with_receipt(private_fixture):
    program, _, _, base = private_fixture
    snapshot.backup()
    ident = _backup_id(base)
    receipt = base / ident / "deployment-receipt.json"
    receipt.write_text(json.dumps({
        "replaced": [{
            "path": str(program),
            "sha256_after": hashlib.sha256(b"candidate\n").hexdigest(),
        }]
    }))
    program.write_text("unrelated edit\n")
    with pytest.raises(RuntimeError, match="differs from the approved deployment"):
        snapshot.restore(ident, "RESTORE-" + ident)
    assert program.read_text() == "unrelated edit\n"


def test_restore_approved_code_only_never_restores_runtime_secrets(private_fixture):
    program, secret, _, base = private_fixture
    snapshot.backup()
    ident = _backup_id(base)
    updated = "candidate\n"
    program.write_text(updated)
    secret.write_text('{"secret":"changed-after-deploy"}\n')
    (base / ident / "deployment-receipt.json").write_text(json.dumps({
        "replaced": [{
            "path": str(program),
            "sha256_after": hashlib.sha256(updated.encode()).hexdigest(),
        }]
    }))
    assert snapshot.restore(ident, "RESTORE-" + ident) == 0
    assert program.read_text() == "before\n"
    assert secret.read_text() == '{"secret":"changed-after-deploy"}\n'


def test_shell_scripts_are_syntax_valid_and_do_not_deploy():
    for path in (SCRIPT_WRAPPER, CAPTURE, VLESS_STOP):
        subprocess.run(["bash", "-n", str(path)], check=True) if path != VLESS_STOP else subprocess.run(
            ["sh", "-n", str(path)], check=True
        )
    wrapper = SCRIPT_WRAPPER.read_text()
    assert "deploy is not available" in wrapper
    capture = CAPTURE.read_text()
    assert "/etc/maxvpn/vless-profiles.json" not in capture.split("PATHS=(")[1].split(")")[0]
    assert "/etc/maxvpn/sing-box-vless.json" not in capture.split("PATHS=(")[1].split(")")[0]
    stop = VLESS_STOP.read_text()
    assert 'vless)' in stop
    assert "Refusing to stop sing-box while LAN routes through VLESS" in stop
    assert '"$SERVICE" stop' in stop
    assert "iptables -F" not in stop
    assert "ip route flush" not in stop
