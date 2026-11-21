import fcntl
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vless_control as vc


@pytest.fixture
def appliance(tmp_path, monkeypatch):
    for name in (
        "SERVICE",
        "MODE_FILE",
        "RUNTIME_LOCK_FILE",
        "WATCHDOG_SCRIPT",
        "WATCHDOG_READY_FILE",
        "PROC_ROOT",
        "DELAY_HISTORY_FILE",
        "BACKUP_DIR",
    ):
        monkeypatch.setattr(vc, name, tmp_path / name)
    vc.SERVICE.touch()
    vc.MODE_FILE.write_text("vpn")
    service = {"running": True, "enabled": True}
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        rc = 0
        if args[0] == str(vc.SERVICE):
            action = args[1]
            if action == "enabled":
                rc = int(not service["enabled"])
            elif action in ("enable", "disable"):
                service["enabled"] = action == "enable"
            elif action in ("start", "stop"):
                service["running"] = action == "start"
        elif args == ["/usr/bin/vpn-lan-off"]:
            vc.MODE_FILE.write_text("wan")
        else:
            pytest.fail("Unexpected external command")
        return SimpleNamespace(returncode=rc, stdout="", stderr="")

    c = vc.VlessControl(tmp_path / "profiles.json", tmp_path / "config.json", run)
    monkeypatch.setattr(c, "_running", lambda **kwargs: service["running"])
    c._save_store(
        {
            "profiles": [
                {"id": 2, "enabled": True, "uuid": "private-fixture"},
                {"id": 5, "enabled": False},
            ],
            "settings": {"wan_fallback_enabled": False},
            "selection": {"mode": "manual", "profile_id": 2},
        },
        backup=False,
    )
    c.config_file.write_text("private-fixture")
    return c, service, calls


def confirmation(c):
    return {"confirm": True, "revision": c.get_state()["delete_revision"]}


def test_delete_all_is_atomic_and_retry_is_safe(appliance):
    c, service, calls = appliance
    c._save_wan_fallback_state({"active": True})
    vc.DELAY_HISTORY_FILE.write_text('{"profiles":{"2":{}}}')
    c.get_selection_history()
    request = confirmation(c)
    assert c.delete_all_profiles(request) == {"deleted": 2, "traffic_mode": "vpn"}
    assert service == {"enabled": False, "running": False}
    state = c.get_state()
    assert state["profiles"] == []
    assert state["desired_selection_mode"] == "auto"
    assert state["wan_fallback_active"] is False
    assert "private-fixture" not in json.dumps(state)
    assert not c.config_file.exists()
    assert c.get_delay_history()["results"] == []
    assert c.get_selection_history()["profile_availability"] == {}
    assert c.monitor_wan_fallback()["active"] is False
    assert c.delete_all_profiles(request)["deleted"] == 0
    assert all(cmd[0] == str(vc.SERVICE) for cmd in calls)


@pytest.mark.parametrize("confirm", [None, False, 1, "true"])
def test_missing_confirmation_has_no_side_effects(appliance, confirm):
    c, _, calls = appliance
    request = confirmation(c)
    with pytest.raises(vc.VlessControlError):
        c.delete_all_profiles(dict(request, confirm=confirm))
    assert not calls
    assert len(c.get_state()["profiles"]) == 2


def test_concurrent_change_invalidates_confirmation(appliance):
    c, _, calls = appliance
    request = confirmation(c)
    c.update_profile(2, {"name": "Edited"})
    with pytest.raises(vc.VlessControlError, match="изменились"):
        c.delete_all_profiles(request)
    assert not calls


def test_vless_route_obeys_kill_switch_and_requires_wan_consent(appliance):
    c, service, calls = appliance
    vc.MODE_FILE.write_text("vless")
    with pytest.raises(vc.VlessControlError, match="Kill Switch"):
        c.delete_all_profiles(dict(confirmation(c), allow_wan=True))
    assert service["running"] and not calls
    c.update_settings({"wan_fallback_enabled": True})
    request = confirmation(c)
    with pytest.raises(vc.VlessControlError, match="WAN"):
        c.delete_all_profiles(request)
    assert not calls
    assert c.delete_all_profiles(dict(request, allow_wan=True))["traffic_mode"] == "wan"
    assert calls.index(["/usr/bin/vpn-lan-off"]) < calls.index(
        [str(vc.SERVICE), "stop"]
    )


def test_store_write_failure_restores_runtime_and_all_profiles(appliance, monkeypatch):
    c, service, _ = appliance
    request = confirmation(c)
    original = c.profile_file.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("private-fixture")

    monkeypatch.setattr(c, "_save_store", fail)
    with pytest.raises(vc.VlessControlError) as exc:
        c.delete_all_profiles(request)
    assert "private-fixture" not in str(exc.value)
    assert c.profile_file.read_bytes() == original
    assert c.config_file.exists() and service == {"running": True, "enabled": True}


def test_cleanup_resumes_after_restart_before_tags_can_be_reused(
    appliance, monkeypatch
):
    c, _, _ = appliance
    request = confirmation(c)
    monkeypatch.setattr(c, "_finish_clear", lambda *_: (_ for _ in ()).throw(OSError()))
    with pytest.raises(OSError):
        c.delete_all_profiles(request)
    assert json.loads(c.profile_file.read_text())["clear_pending"]
    restarted = vc.VlessControl(c.profile_file, c.config_file, c.command_runner)
    restarted.get_selection_history()
    stored = json.loads(c.profile_file.read_text())
    assert not c.config_file.exists() and stored["profiles"] == []
    assert "clear_pending" not in stored


def test_collection_http_handler_validates_and_returns_counts(appliance, monkeypatch):
    monkeypatch.setenv("MAXVPN_APPLIANCE_ROOT", str(appliance[0].profile_file.parent))
    from appliance.maxvpn import server

    c, _, _ = appliance
    monkeypatch.setattr(server, "VLESS_CONTROL", c)
    request = confirmation(c)
    handler = SimpleNamespace(
        path="/api/appliance/v1/vless/profiles",
        read_json=lambda: {},
        send_json=lambda *v: v,
        send_error_json=lambda *v: v,
    )
    status, message = server.Handler.do_DELETE(handler)
    assert status == 422 and "Подтвердите" in message
    handler.read_json = lambda: request
    assert server.Handler.do_DELETE(handler) == (
        200,
        {"deleted": 2, "traffic_mode": "vpn"},
    )


def test_failed_wan_transition_does_not_stop_service_or_remove_profiles(
    appliance, monkeypatch
):
    c, service, _ = appliance
    vc.MODE_FILE.write_text("vless")
    c.update_settings({"wan_fallback_enabled": True})

    def fail(mode):
        raise vc.VlessControlError("route failure")

    monkeypatch.setattr(c, "set_mode", fail)
    with pytest.raises(vc.VlessControlError):
        c.delete_all_profiles(dict(confirmation(c), allow_wan=True))
    assert len(c._load_store()["profiles"]) == 2
    assert service == {"running": True, "enabled": True}


def _emulate_vless_mode_switch(c, monkeypatch):
    switched = []

    def switch(mode, **_kwargs):
        switched.append(mode)
        vc.MODE_FILE.write_text(mode)
        return {}

    monkeypatch.setattr(c, "set_mode", switch)
    return switched


def test_vless_delete_rolls_back_wan_route_when_store_write_fails(
    appliance, monkeypatch
):
    c, service, _ = appliance
    vc.MODE_FILE.write_text("vless")
    c.update_settings({"wan_fallback_enabled": True})
    before = c.profile_file.read_bytes()
    switched = _emulate_vless_mode_switch(c, monkeypatch)
    request = dict(confirmation(c), allow_wan=True)

    def fail_write(*_args, **_kwargs):
        raise OSError("private-fixture")

    monkeypatch.setattr(c, "_save_store", fail_write)
    with pytest.raises(vc.VlessControlError, match="маршрут VLESS восстановлен"):
        c.delete_all_profiles(request)

    assert switched == ["wan", "vless"]
    assert vc.MODE_FILE.read_text() == "vless"
    assert c.profile_file.read_bytes() == before
    assert service == {"enabled": True, "running": True}


def test_vless_delete_rolls_back_wan_route_when_stop_fails(appliance, monkeypatch):
    c, service, _ = appliance
    vc.MODE_FILE.write_text("vless")
    c.update_settings({"wan_fallback_enabled": True})
    switched = _emulate_vless_mode_switch(c, monkeypatch)
    request = dict(confirmation(c), allow_wan=True)
    original_checked = c._checked

    def checked(args, action, **kwargs):
        if args == [str(vc.SERVICE), "stop"]:
            raise vc.VlessControlError("Cannot stop service")
        return original_checked(args, action, **kwargs)

    monkeypatch.setattr(c, "_checked", checked)
    with pytest.raises(vc.VlessControlError, match="маршрут VLESS восстановлен"):
        c.delete_all_profiles(request)

    assert switched == ["wan", "vless"]
    assert len(c._load_store()["profiles"]) == 2
    assert service == {"enabled": True, "running": True}


def test_vless_delete_never_restores_route_after_store_commit(
    appliance, monkeypatch
):
    c, service, _ = appliance
    vc.MODE_FILE.write_text("vless")
    c.update_settings({"wan_fallback_enabled": True})
    switched = _emulate_vless_mode_switch(c, monkeypatch)
    request = dict(confirmation(c), allow_wan=True)
    monkeypatch.setattr(
        c,
        "_finish_clear",
        lambda *_: (_ for _ in ()).throw(OSError("cleanup failed")),
    )
    with pytest.raises(
        vc.VlessControlError, match="Удаление профилей зафиксировано"
    ):
        c.delete_all_profiles(request)

    assert switched == ["wan"]
    assert vc.MODE_FILE.read_text() == "wan"
    saved = json.loads(c.profile_file.read_text())
    assert saved["clear_pending"] is True
    assert saved["profiles"] == []
    assert service == {"enabled": False, "running": False}


def test_failed_vless_rollback_reports_wan_and_keeps_profiles(
    appliance, monkeypatch
):
    c, service, _ = appliance
    vc.MODE_FILE.write_text("vless")
    c.update_settings({"wan_fallback_enabled": True})
    request = dict(confirmation(c), allow_wan=True)
    switched = []

    def switch(mode, **_kwargs):
        switched.append(mode)
        if mode == "vless":
            raise vc.VlessControlError("VLESS restart failed")
        vc.MODE_FILE.write_text(mode)

    monkeypatch.setattr(c, "set_mode", switch)
    monkeypatch.setattr(
        c, "_clear_inactive_profiles",
        lambda *_: (_ for _ in ()).throw(OSError("aborted")),
    )
    with pytest.raises(vc.VlessControlError, match="LAN остаётся в WAN"):
        c.delete_all_profiles(request)
    assert switched == ["wan", "vless"]
    assert vc.MODE_FILE.read_text() == "wan"
    assert len(c._load_store()["profiles"]) == 2
    assert service == {"enabled": True, "running": True}


def _can_take_routing_lock():
    with vc.RUNTIME_LOCK_FILE.open("a") as probe:
        try:
            fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(probe.fileno(), fcntl.LOCK_UN)
        return True


def test_bulk_delete_uses_smart_routing_apply_lock():
    from appliance.maxvpn import server

    # Tests may set MAXVPN_APPLIANCE_ROOT for server.py only. The deployed
    # appliance has the same root for both modules; verify the common
    # lock naming convention without assuming that unit-test environment.
    assert vc.RUNTIME_LOCK_FILE == vc.ROOT / "run" / "apply.lock"
    assert server.LOCK == server.ROOT / "run" / "apply.lock"


def test_bulk_delete_holds_routing_lock_during_wan_transition_and_commit(
    appliance, monkeypatch
):
    c, service, _ = appliance
    vc.MODE_FILE.write_text("vless")
    c.update_settings({"wan_fallback_enabled": True})
    request = dict(confirmation(c), allow_wan=True)
    observed = []

    def switch(mode, **_kwargs):
        observed.append(("switch", mode, _can_take_routing_lock()))
        vc.MODE_FILE.write_text(mode)
        return {}

    original_clear = c._clear_inactive_profiles

    def clear(store, revision):
        observed.append(("clear", vc.MODE_FILE.read_text(), _can_take_routing_lock()))
        return original_clear(store, revision)

    monkeypatch.setattr(c, "set_mode", switch)
    monkeypatch.setattr(c, "_clear_inactive_profiles", clear)
    assert _can_take_routing_lock()
    assert c.delete_all_profiles(request)["traffic_mode"] == "wan"
    assert observed == [
        ("switch", "wan", False),
        ("clear", "wan", False),
    ]
    assert _can_take_routing_lock()
    assert service == {"enabled": False, "running": False}


def test_bulk_delete_holds_routing_lock_during_error_rollback(
    appliance, monkeypatch
):
    c, service, _ = appliance
    vc.MODE_FILE.write_text("vless")
    c.update_settings({"wan_fallback_enabled": True})
    request = dict(confirmation(c), allow_wan=True)
    original_clear = c._clear_inactive_profiles
    observed = []

    def switch(mode, **_kwargs):
        observed.append((mode, _can_take_routing_lock()))
        vc.MODE_FILE.write_text(mode)
        return {}

    def fail_clear(*_args):
        assert not _can_take_routing_lock()
        raise vc.VlessControlError("Cannot clear")

    monkeypatch.setattr(c, "set_mode", switch)
    monkeypatch.setattr(c, "_clear_inactive_profiles", fail_clear)
    with pytest.raises(vc.VlessControlError, match="маршрут VLESS восстановлен"):
        c.delete_all_profiles(request)
    assert observed == [("wan", False), ("vless", False)]
    assert _can_take_routing_lock()
    assert vc.MODE_FILE.read_text() == "vless"
    assert len(c._load_store()["profiles"]) == 2
    assert service == {"enabled": True, "running": True}


def test_legacy_unlocked_watchdog_blocks_bulk_delete_before_route_mutation(
    appliance, monkeypatch
):
    c, service, calls = appliance
    vc.MODE_FILE.write_text("vless")
    c.update_settings({"wan_fallback_enabled": True})
    vc.WATCHDOG_SCRIPT.write_text(
        "#!/bin/sh\\n# old watchdog without shared route lock\\n"
    )
    before = c.profile_file.read_bytes()
    with pytest.raises(vc.VlessControlError, match="watchdog"):
        c.delete_all_profiles(dict(confirmation(c), allow_wan=True))

    assert c.profile_file.read_bytes() == before
    assert vc.MODE_FILE.read_text() == "vless"
    assert service == {"enabled": True, "running": True}
    assert calls == []


def test_reviewed_shared_lock_watchdog_permits_vless_delete(
    appliance, monkeypatch
):
    c, service, calls = appliance
    vc.MODE_FILE.write_text("vless")
    c.update_settings({"wan_fallback_enabled": True})
    script = (
        Path(__file__).resolve().parents[1]
        / "compat"
        / "brume3-watchdog-locked.sh"
    )
    vc.WATCHDOG_SCRIPT.write_text(script.read_text(encoding="utf-8"))
    # Merely replacing a watchdog script on disk is not enough: the
    # already-running sh process can still have the old unguarded code.
    with pytest.raises(vc.VlessControlError, match="перезапустите watchdog"):
        c.delete_all_profiles(dict(confirmation(c), allow_wan=True))
    ready = vc.WATCHDOG_READY_FILE
    proc = vc.PROC_ROOT / "4242"
    proc.mkdir(parents=True)
    proc.joinpath("stat").write_text(
        "4242 (sh) S " + " ".join(["0"] * 18 + ["12345"]) + "\\n"
    )
    proc.joinpath("cmdline").write_bytes(
        b"/bin/sh\\0/usr/bin/maxvpn-vless-watchdog\\0"
    )
    ready.write_text("4242 12345\\n")
    switched = _emulate_vless_mode_switch(c, monkeypatch)

    result = c.delete_all_profiles(dict(confirmation(c), allow_wan=True))
    assert result == {"deleted": 2, "traffic_mode": "wan"}
    assert switched == ["wan"]
    assert service == {"enabled": False, "running": False}
    assert c.get_state()["profiles"] == []
