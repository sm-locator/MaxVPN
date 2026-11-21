"""Shared routing flock contract for the GL-MT5000 watchdog candidate.

This script is not installed by CI or by any appliance build step.
"""
import fcntl
from pathlib import Path
import re
import subprocess
import time

WATCHDOG = (
    Path(__file__).resolve().parents[1]
    / "compat"
    / "brume3-watchdog-locked.sh"
)


def _harness():
    src = WATCHDOG.read_text(encoding="utf-8")
    match = re.search(r"(?ms)^with_routing_lock\(\) \(\n.*?^\)\n", src)
    assert match, "watchdog must define an isolated route-guard function"
    return (
        match.group()
        + '\nROUTE_LOCK="$1"\nRUNTIME_MODE_FILE="$2"\nshift 2\n'
        + 'with_routing_lock "$@"\n'
    )


def test_watchdog_has_a_shared_lock_guard_and_preserves_failure_policy():
    source = WATCHDOG.read_text(encoding="utf-8")
    subprocess.run(["sh", "-n", str(WATCHDOG)], check=True)
    assert "ROUTE_LOCK=${MAXVPN_APPLIANCE_ROUTE_LOCK:-/opt/maxvpn-appliance/run/apply.lock}" in source
    assert 'exec 9>>"$ROUTE_LOCK"' in source
    assert "/usr/bin/flock -x 9" in source
    assert "/usr/bin/flock -u 9" in source
    assert "MAXVPN_SHARED_ROUTE_LOCK_V1" in source
    assert "watchdog-shared-lock-v1.status" in source
    assert '"/proc/$/stat"' in source
    assert '"$RUNTIME_MODE_FILE" 2>/dev/null || true' in source
    assert 'if with_routing_lock "$VLESS_ON"; then' in source
    assert 'elif with_routing_lock "$VLESS_ON"; then' in source
    assert 'if with_routing_lock "$SING_BOX_INIT" "$SERVICE_ACTION"; then' in source
    assert re.search(r"(?m)^\s+(if|elif) \"\$VLESS_ON\"; then", source) is None
    for item in (
        "FAILURE_THRESHOLD=3",
        "RESTART_COOLDOWN_TICKS=6",
        "POLICY_REPAIR_COOLDOWN_TICKS=6",
        "sleep 5",
        'iptables -C MAXVPN_LAN_FORWARD -i br-lan -o eth1 -j DROP',
        'ip6tables -C MAXVPN_LAN6_FORWARD -i br-lan -j DROP',
    ):
        assert item in source


def test_watchdog_guard_serializes_with_python_flock_and_rechecks_mode(tmp_path):
    lock = tmp_path / "apply.lock"
    mode = tmp_path / "runtime-mode"
    output = tmp_path / "invoked"
    mode.write_text("vless")
    runner = 'echo invoked > "$1"'
    cmd = [
        "sh", "-c", _harness(), "watchdog-test",
        str(lock), str(mode), "sh", "-c", runner, "worker", str(output),
    ]
    with lock.open("a") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX)
        child = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            time.sleep(0.15)
            assert child.poll() is None, "watchdog must block on shared flock"
            assert not output.exists()
            mode.write_text("wan")
        finally:
            fcntl.flock(held.fileno(), fcntl.LOCK_UN)
        stdout, stderr = child.communicate(timeout=3)
    assert child.returncode == 2, stderr.decode()
    assert not output.exists(), "WAN transition must suppress delayed VLESS repair"


def test_watchdog_guard_runs_helper_in_vless_mode(tmp_path):
    lock = tmp_path / "apply.lock"
    mode = tmp_path / "runtime-mode"
    output = tmp_path / "invoked"
    mode.write_text("vless")
    script = _harness()
    result = subprocess.run(
        [
            "sh", "-c", script, "watchdog-test", str(lock), str(mode),
            "sh", "-c", 'echo invoked > "$1"', "worker", str(output),
        ],
        check=False,
        capture_output=True,
        timeout=3,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert output.read_text().strip() == "invoked"
