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
