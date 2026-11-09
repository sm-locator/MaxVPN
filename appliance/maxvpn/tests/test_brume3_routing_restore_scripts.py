from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[3]
INSTALLER = REPO / "deploy_maxvpn_brume3_routing_restore_only.sh"
ROLLBACK = REPO / "rollback_maxvpn_brume3_routing_restore_only.sh"
STAMP = "20261103-120000-4242"


def remote_body(script: Path) -> str:
    text = script.read_text(encoding="utf-8")
    start = text.index("<<'REMOTE'\n") + len("<<'REMOTE'\n")
    return text[start : text.index("\nREMOTE", start)]


def configured(
    script: Path, app: Path, hotplug: Path, stage: Path | None = None
) -> str:
    body = remote_body(script)
    body = body.replace('APP_DIR="/opt/maxvpn-appliance"', f'APP_DIR="{app}"')
    body = body.replace(
        'HOTPLUG_DIR="/etc/hotplug.d/iface"', f'HOTPLUG_DIR="{hotplug}"'
    )
    if stage:
        body = body.replace(
            'STAGE="/tmp/maxvpn-brume3-routing-restore-${STAMP}"', f'STAGE="{stage}"'
        )
    body = body.replace("/usr/bin/python3", sys.executable)
    return body


def run(body: str, *args: str):
    return subprocess.run(
        ["sh", "-s", "--", *args], input=body, text=True, capture_output=True
    )


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install(tmp_path: Path, original_hotplug: bool = True):
    app, hotplug_dir, stage = tmp_path / "app", tmp_path / "hotplug", tmp_path / "stage"
    app.mkdir()
    hotplug_dir.mkdir()
    stage.mkdir()
    server = app / "server.py"
    server.write_text("VALUE = 'old'\n")
    server.chmod(0o640)
    hook = hotplug_dir / "99-maxvpn-restore-routing"
    if original_hotplug:
        hook.write_text("#!/bin/sh\nexit 0\n")
        hook.chmod(0o700)
    new_server, new_hook = stage / "server.py", stage / "99-maxvpn-restore-routing"
    new_server.write_text("VALUE = 'new'\n")
    new_hook.write_text("#!/bin/sh\nexit 0\n")
    result = run(
        configured(INSTALLER, app, hotplug_dir, stage),
        STAMP,
        sha(new_server),
        sha(new_hook),
    )
    assert result.returncode == 0, result.stderr
    return app, hotplug_dir, server, hook


def test_install_and_rollback_restore_bytes_metadata_and_are_repeatable(tmp_path):
    app, hotplug_dir, server, hook = install(tmp_path)
    backup = app / "backups" / f"brume3-routing-restore-{STAMP}"
    assert server.read_text() == "VALUE = 'new'\n"
    assert hook.stat().st_mode & 0o777 == 0o755
    assert (backup / "SHA256SUMS").is_file()
    assert (backup / "server.py").stat().st_mode & 0o777 == 0o640
    assert (backup / "99-maxvpn-restore-routing").stat().st_mode & 0o777 == 0o700

    for _ in range(2):
        result = run(configured(ROLLBACK, app, hotplug_dir), STAMP)
        assert result.returncode == 0, result.stderr
    assert server.read_text() == "VALUE = 'old'\n"
    assert hook.stat().st_mode & 0o777 == 0o700


def test_rollback_removes_hook_recorded_as_absent(tmp_path):
    app, hotplug_dir, server, hook = install(tmp_path, original_hotplug=False)
    assert hook.exists()
    result = run(configured(ROLLBACK, app, hotplug_dir), STAMP)
    assert result.returncode == 0, result.stderr
    assert server.read_text() == "VALUE = 'old'\n"
    assert not hook.exists()


def test_corrupt_backup_refuses_before_changing_live_files(tmp_path):
    app, hotplug_dir, server, hook = install(tmp_path)
    backup = app / "backups" / f"brume3-routing-restore-{STAMP}"
    before = server.read_bytes(), hook.read_bytes()
    (backup / "server.py").write_text("VALUE = 'tampered'\n")
    result = run(configured(ROLLBACK, app, hotplug_dir), STAMP)
    assert result.returncode != 0
    assert (server.read_bytes(), hook.read_bytes()) == before


def test_installer_rejects_dangling_hotplug_symlink_before_replacing(tmp_path):
    app, hotplug_dir, stage = tmp_path / "app", tmp_path / "hotplug", tmp_path / "stage"
    app.mkdir()
    hotplug_dir.mkdir()
    stage.mkdir()
    server = app / "server.py"
    server.write_text("VALUE = 'old'\n")
    hook = hotplug_dir / "99-maxvpn-restore-routing"
    hook.symlink_to(hotplug_dir / "missing")
    new_server, new_hook = stage / "server.py", stage / "99-maxvpn-restore-routing"
    new_server.write_text("VALUE = 'new'\n")
    new_hook.write_text("#!/bin/sh\nexit 0\n")
    result = run(
        configured(INSTALLER, app, hotplug_dir, stage),
        STAMP,
        sha(new_server),
        sha(new_hook),
    )
    assert result.returncode != 0
    assert server.read_text() == "VALUE = 'old'\n"
    assert not (app / "backups" / f"brume3-routing-restore-{STAMP}").exists()


@pytest.mark.parametrize("script", [INSTALLER, ROLLBACK])
def test_scripts_are_shell_syntax_valid(script):
    subprocess.run(["bash", "-n", str(script)], check=True)
