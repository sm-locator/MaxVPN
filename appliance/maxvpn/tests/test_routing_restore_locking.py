import os
from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

os.environ["MAXVPN_APPLIANCE_ROOT"] = tempfile.mkdtemp(
    prefix="maxvpn-routing-lock-test-"
)

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))
import server as appliance  # noqa: E402

HOTPLUG = MODULE_DIR / "hotplug.d" / "iface" / "99-maxvpn-restore-routing"


def test_routing_lock_blocks_until_another_process_releases_it(tmp_path, monkeypatch):
    lock_path = tmp_path / "apply.lock"
    monkeypatch.setattr(appliance, "LOCK", lock_path)
    holder_code = """
import fcntl
import sys

with open(sys.argv[1], "a") as lock_file:
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
    print("locked", flush=True)
    sys.stdin.read(1)
"""
    holder = subprocess.Popen(
        [sys.executable, "-c", holder_code, str(lock_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    acquired = threading.Event()

    def acquire_lock():
        with appliance.routing_lock():
            acquired.set()

    worker = threading.Thread(target=acquire_lock)
    try:
        assert holder.stdout.readline().strip() == "locked"
        worker.start()
        assert not acquired.wait(0.15)

        holder.stdin.write("x")
        holder.stdin.flush()
        assert holder.wait(timeout=2) == 0
        assert acquired.wait(2)
        worker.join(timeout=2)
        assert not worker.is_alive()
    finally:
        if holder.poll() is None:
            holder.terminate()
            holder.wait(timeout=2)
        worker.join(timeout=2)


def test_apply_routing_acquires_the_shared_lock(monkeypatch):
    events = []

    @contextmanager
    def fake_lock():
        events.append("lock")
        yield
        events.append("unlock")

    monkeypatch.setattr(appliance, "routing_lock", fake_lock)
    monkeypatch.setattr(
        appliance, "_apply_routing", lambda: events.append("apply") or {"ok": True}
    )

    assert appliance.apply_routing() == {"ok": True}
    assert events == ["lock", "apply", "unlock"]


def test_restore_exit_code_requires_forced_apply_and_firewall_verification(
    monkeypatch,
):
    events = []

    def fake_baseline(force=False):
        events.append(("baseline", force))
        return True

    def fake_firewall():
        events.append("firewall")
        return {"mode": "vless", "nat_jump_count": 1}

    monkeypatch.setattr(appliance, "ensure_applied_baseline", fake_baseline)
    monkeypatch.setattr(appliance, "restore_runtime_firewall", fake_firewall)

    assert appliance.restore_routing_exit_code() == 0
    assert events == [("baseline", True), "firewall"]

    events.clear()
    monkeypatch.setattr(
        appliance,
        "ensure_applied_baseline",
        lambda force=False: events.append(("baseline", force)) or False,
    )

    assert appliance.restore_routing_exit_code() == 1
    assert events == [("baseline", True)]


def test_restore_cli_does_not_start_http_server_or_vless_monitor(monkeypatch):
    calls = []
    monkeypatch.setattr(appliance, "seed_rules", lambda: calls.append("seed"))
    monkeypatch.setattr(
        appliance, "restore_routing_exit_code", lambda: calls.append("restore") or 0
    )

    def unexpected_start(*args, **kwargs):
        raise AssertionError("restore CLI must not start the normal service")

    monkeypatch.setattr(appliance, "discover_network", unexpected_start)
    monkeypatch.setattr(appliance, "ThreadingHTTPServer", unexpected_start)
    monkeypatch.setattr(appliance.threading, "Thread", unexpected_start)

    assert appliance.main(["--restore-routing"]) == 0
    assert calls == ["seed", "restore"]


def test_wan_hotplug_is_syntax_valid_and_only_runs_restore_cli():
    script = HOTPLUG.read_text(encoding="utf-8")

    assert '[ "$ACTION" = "ifup" ] && [ "$INTERFACE" = "wan" ] || exit 0' in script
    assert (
        "exec /usr/bin/python3 /opt/maxvpn-appliance/server.py --restore-routing"
        in script
    )
    assert "ThreadingHTTPServer" not in script
    subprocess.run(["sh", "-n", str(HOTPLUG)], check=True)
