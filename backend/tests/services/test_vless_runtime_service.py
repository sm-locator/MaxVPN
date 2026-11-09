from __future__ import annotations

from types import SimpleNamespace

import pytest
from backend.models.vless_config import (
    VlessRealityConfig,
    VlessServerConfig,
)
from backend.services.vless_runtime_service import VlessRuntimeService


def sample_server():
    return VlessServerConfig(
        name="Test profile",
        address="example.com",
        port=443,
        uuid="00000000-0000-0000-0000-000000000000",
        flow="xtls-rprx-vision",
        network="tcp",
        reality=VlessRealityConfig(
            public_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            server_name="example.com",
            short_id="abcd",
            fingerprint="firefox",
        ),
    )


class FakeProfileService:
    def __init__(self, *, present=True, enabled=True):
        self.present = present
        self.enabled = enabled
        self.server = sample_server()

    def get(self, user_id: int):
        if not self.present:
            return None
        return SimpleNamespace(
            id=1,
            name="Test profile",
            enabled=self.enabled,
        )

    def get_server(self, user_id: int):
        if not self.present:
            return None
        return self.server

    def list(self, user_id: int):
        if not self.present:
            return []
        return [
            SimpleNamespace(
                id=1,
                name="Test profile",
                address="example.com",
                port=443,
            )
        ]


class FakeController:
    def __init__(self, *, installed=False, running=False):
        self.installed = installed
        self.running = running
        self.calls = []
        self.config = None
        self.backups = {}
        self.start_failures = 0

    def status(self):
        self.calls.append(("status",))
        return {
            "installed": self.installed,
            "running": self.running,
        }

    def install_verified_binary(self):
        self.calls.append(("install_binary",))

    def install_service_script(self):
        self.calls.append(("install_service",))
        self.installed = True

    def install_config(self, config):
        self.calls.append(("install_config",))
        self.config = config

    def backup_config(self):
        self.calls.append(("backup_config",))
        if self.config is None:
            return None
        token = f"backup-{len(self.backups) + 1}"
        self.backups[token] = self.config
        return token

    def restore_config(self, token):
        self.calls.append(("restore_config", token))
        self.config = self.backups.pop(token) if token is not None else None

    def discard_config_backup(self, token):
        self.calls.append(("discard_config_backup", token))
        if token is not None:
            self.backups.pop(token, None)

    def start(self):
        self.calls.append(("start",))
        if self.start_failures:
            self.start_failures -= 1
            raise RuntimeError("simulated sing-box startup failure")
        self.installed = True
        self.running = True

    def stop(self):
        self.calls.append(("stop",))
        self.running = False

    def disable_autostart(self):
        self.calls.append(("disable_autostart",))


def make_service(*, present=True, enabled=True, controller=None):
    profiles = FakeProfileService(present=present, enabled=enabled)
    remote = controller or FakeController()
    return VlessRuntimeService(profiles, remote), remote


def test_prepare_installs_binary_service_and_config_without_starting():
    service, controller = make_service()

    result = service.prepare(user_id=7)

    assert result["action"] == "prepared"
    assert result["prepared"] is True
    assert result["running"] is False
    assert result["interface"] == "maxvpn0"
    assert result["lan_routing_enabled"] is False

    assert controller.calls.index(("install_binary",)) < controller.calls.index(
        ("install_service",)
    )
    assert controller.calls.index(("install_service",)) < controller.calls.index(
        ("install_config",)
    )
    assert ("start",) not in controller.calls

    assert controller.config["inbounds"][0]["auto_route"] is False
    assert controller.config["inbounds"][0]["interface_name"] == "maxvpn0"
    assert controller.config["route"]["final"] == "vless-out"


def test_missing_profile_fails_before_remote_operations():
    service, controller = make_service(present=False)

    with pytest.raises(LookupError, match="vless_profile_not_found"):
        service.prepare(user_id=7)

    assert not any(
        call[0].startswith("install_") or call[0] == "start"
        for call in controller.calls
    )


def test_disabled_profile_fails_before_remote_operations():
    service, controller = make_service(enabled=False)

    with pytest.raises(ValueError, match="vless_profile_disabled"):
        service.start(user_id=7)

    assert not any(call[0] in ("install_binary", "start") for call in controller.calls)


def test_prepare_refuses_to_replace_config_while_process_is_running():
    controller = FakeController(installed=True, running=True)
    service, controller = make_service(controller=controller)

    with pytest.raises(RuntimeError, match="sing-box is running"):
        service.prepare(user_id=7)

    assert not any(call[0].startswith("install_") for call in controller.calls)


def test_start_installs_config_and_starts_runtime():
    service, controller = make_service()

    result = service.start(user_id=7)

    assert result["action"] == "started"
    assert result["running"] is True
    assert result["lan_routing_enabled"] is False
    assert controller.calls[-1] == ("status",)
    assert ("start",) in controller.calls


def test_start_reloads_valid_profile_if_process_already_running():
    controller = FakeController(installed=True, running=True)
    service, controller = make_service(controller=controller)

    result = service.start(user_id=7)

    assert result["running"] is True
    assert ("stop",) in controller.calls
    assert ("install_config",) in controller.calls
    assert controller.calls.index(("stop",)) < controller.calls.index(("start",))


def test_stop_disables_autostart_when_service_is_installed():
    controller = FakeController(installed=True, running=True)
    service, controller = make_service(controller=controller)

    result = service.stop()

    assert result["action"] == "stopped"
    assert result["running"] is False
    assert result["lan_routing_enabled"] is False
    assert result["message"] == "sing-box stop requested"
    assert ("stop",) in controller.calls
    assert ("disable_autostart",) in controller.calls


def test_stop_delegates_vless_lan_fallback_and_shutdown_together():
    class TrafficController:
        mode = "vless"

        def get_mode(self):
            return self.mode

    traffic_controller = TrafficController()
    controller = FakeController(installed=True, running=True)

    def stop_with_lan_fallback():
        controller.calls.append(("stop_with_lan_fallback",))
        traffic_controller.mode = "wan"
        controller.running = False
        return True

    controller.stop_with_lan_fallback = stop_with_lan_fallback
    service = VlessRuntimeService(
        FakeProfileService(), controller, traffic_controller=traffic_controller
    )

    result = service.stop()

    assert controller.calls == [("stop_with_lan_fallback",), ("status",)]
    assert result["action"] == "stopped"
    assert result["lan_routing_enabled"] is False
    assert "returned to WAN before stopping" in result["message"]


def test_stop_does_not_retry_outside_router_lock_when_wan_transition_fails():
    controller = FakeController(installed=True, running=True)

    def stop_with_lan_fallback():
        raise RuntimeError("simulated WAN transition failure")

    controller.stop_with_lan_fallback = stop_with_lan_fallback
    service = VlessRuntimeService(
        FakeProfileService(), controller, traffic_controller=object()
    )

    with pytest.raises(RuntimeError, match="simulated WAN transition failure"):
        service.stop()

    assert controller.calls == []


def test_status_explicitly_reports_routing_is_not_enabled():
    service, _ = make_service()

    status = service.status()

    assert status["interface"] == "maxvpn0"
    assert status["lan_routing_enabled"] is False
    assert "has not been configured" in status["message"]


class ActiveInfoController(FakeController):
    def runtime_server_info(self):
        return {
            "selected_outbound": "vless-auto",
            "active_outbound": "vless-profile-1",
            "selection_mode": "auto",
            "runtime_config_mode": "multi_profile",
        }


def test_status_resolves_active_vless_profile_to_server_name_and_address():
    controller = ActiveInfoController(installed=True, running=True)
    service, _ = make_service(controller=controller)

    status = service.status(user_id=7)

    assert status["active_outbound"] == "vless-profile-1"
    assert status["active_server_name"] == "Test profile"
    assert status["active_server_address"] == "example.com"
    assert status["active_server_port"] == 443


def test_start_failure_restores_previous_config_and_running_state():
    controller = FakeController(installed=True, running=True)
    previous_config = {"previous": "working-config"}
    controller.config = previous_config.copy()
    controller.start_failures = 1
    service, _ = make_service(controller=controller)

    with pytest.raises(RuntimeError, match="simulated sing-box startup failure"):
        service.start(user_id=7)

    assert controller.config == previous_config
    assert controller.running is True
    assert ("restore_config", "backup-1") in controller.calls
    assert not controller.backups


def test_start_failure_when_stopped_restores_previous_config_and_stays_stopped():
    controller = FakeController(installed=True, running=False)
    previous_config = {"previous": "prepared-config"}
    controller.config = previous_config.copy()
    controller.start_failures = 1
    service, _ = make_service(controller=controller)

    with pytest.raises(RuntimeError, match="simulated sing-box startup failure"):
        service.start(user_id=7)

    assert controller.config == previous_config
    assert controller.running is False


class FakeApplianceSyncProfileService(FakeProfileService):
    def __init__(self, local_only=None):
        super().__init__(present=True, enabled=True)
        self.sync_calls = []
        self.local_only = local_only or []

    def appliance_sync_status(self, user_id, store):
        self.sync_calls.append(("status", user_id))
        return {
            "connected": True,
            "sync_required": False,
            "local_profile_count": 1,
            "appliance_profile_count": 1,
            "on_router_only": [],
            "local_only": self.local_only,
            "updated": [],
            "settings_changed": False,
            "local_settings": {"urltest_interval": "3m", "urltest_tolerance_ms": 50},
            "appliance_settings": {
                "urltest_interval": "3m",
                "urltest_tolerance_ms": 50,
            },
        }

    def synchronize_from_appliance(self, user_id, store):
        self.sync_calls.append(("sync", user_id))
        return {
            "imported": 0,
            "updated": 0,
            "deleted": 0,
            "unchanged": 1,
            "profiles": 1,
            "settings_synchronized": True,
        }


class FakeApplianceSyncController(FakeController):
    def read_appliance_vless_store(self):
        return {
            "version": 1,
            "profiles": [
                {
                    "id": 17,
                    "name": "Test profile",
                    "enabled": True,
                    "address": "example.com",
                    "port": 443,
                    "uuid": "00000000-0000-0000-0000-000000000000",
                }
            ],
            "settings": {"urltest_interval": "3m", "urltest_tolerance_ms": 50},
            "selection": {"mode": "manual", "profile_id": 17},
        }

    def runtime_server_info(self):
        return {
            "selected_outbound": "vless-profile-17",
            "active_outbound": "vless-profile-17",
            "active_server_address": "example.com",
            "active_server_port": 443,
            "selection_mode": "manual",
            "runtime_config_mode": "multi_profile",
        }


def test_appliance_sync_status_reports_manual_selection_signature():
    profiles = FakeApplianceSyncProfileService()
    controller = FakeApplianceSyncController(installed=True, running=True)
    service = VlessRuntimeService(profiles, controller)

    result = service.appliance_sync_status(7)

    assert result["selection_mode"] == "manual"
    assert result["selected_profile"] == "Test profile"
    assert result["selection_signature"] == "manual:example.com:443"
    assert result["runtime_selection_mode"] == "manual"
    assert result["selection_pending"] is False
    assert result["sync_required"] is False


def test_appliance_sync_updates_local_state_without_restarting_router():
    profiles = FakeApplianceSyncProfileService()
    controller = FakeApplianceSyncController(installed=True, running=True)
    service = VlessRuntimeService(profiles, controller)

    result = service.synchronize_from_appliance(7)

    assert result["synced"] is True
    assert result["sync_result"]["profiles"] == 1
    assert profiles.sync_calls == [("status", 7), ("sync", 7), ("status", 7)]
    assert not any(
        call[0] in {"install_config", "start", "stop"} for call in controller.calls
    )


def test_appliance_sync_status_uses_saved_manual_pin_when_runtime_is_stopped():
    profiles = FakeApplianceSyncProfileService()
    controller = FakeApplianceSyncController(installed=True, running=False)
    service = VlessRuntimeService(profiles, controller)

    result = service.appliance_sync_status(7)

    assert result["selection_mode"] == "manual"
    assert result["selected_profile"] == "Test profile"
    assert result["selection_signature"] == "manual:example.com:443"
    assert result["runtime_selection_mode"] == "unknown"
    assert result["selection_pending"] is True


def test_appliance_sync_status_distinguishes_saved_manual_choice_from_live_auto_mode():
    profiles = FakeApplianceSyncProfileService()
    controller = FakeApplianceSyncController(installed=True, running=True)
    controller.runtime_server_info = lambda: {
        "selected_outbound": "vless-auto",
        "active_outbound": "vless-profile-1",
        "active_server_address": "example.com",
        "active_server_port": 443,
        "selection_mode": "auto",
        "runtime_config_mode": "multi_profile",
    }
    service = VlessRuntimeService(profiles, controller)

    result = service.appliance_sync_status(7)

    assert result["selection_mode"] == "manual"
    assert result["selected_profile"] == "Test profile"
    assert result["selection_signature"] == "manual:example.com:443"
    assert result["runtime_selection_mode"] == "auto"
    assert result["runtime_selected_outbound"] == "vless-auto"
    assert result["runtime_active_outbound"] == "vless-profile-1"
    assert result["selection_pending"] is True


def test_appliance_sync_requires_confirmation_before_deleting_local_only_profiles():
    profiles = FakeApplianceSyncProfileService(
        local_only=[{"id": 9, "name": "Local-only"}]
    )
    controller = FakeApplianceSyncController(installed=True, running=True)
    service = VlessRuntimeService(profiles, controller)

    with pytest.raises(ValueError, match="Подтвердите удаление"):
        service.synchronize_from_appliance(7)

    assert not any(call[0] == "sync" for call in profiles.sync_calls)

    result = service.synchronize_from_appliance(7, confirm_delete_local_only=True)
    assert result["synced"] is True
    assert any(call[0] == "sync" for call in profiles.sync_calls)


def test_enable_lan_routing_reports_watchdog_warning_but_keeps_routing_enabled():
    class WarningTrafficController:
        def __init__(self):
            self.calls = []

        def enable_vless_mode(self):
            self.calls.append(("enable_vless_mode",))
            return "watchdog start failed"

        def get_mode(self):
            self.calls.append(("get_mode",))
            return "vless"

    traffic_controller = WarningTrafficController()
    controller = FakeController(installed=True, running=True)
    service = VlessRuntimeService(
        FakeProfileService(),
        controller,
        traffic_controller=traffic_controller,
    )

    result = service.enable_lan_routing(user_id=7)

    assert result["lan_routing_enabled"] is True
    assert result["action"] == "lan-routing-enabled"
    assert "watchdog did not start" in result["message"]
    assert "watchdog start failed" in result["message"]
    assert traffic_controller.calls == [
        ("enable_vless_mode",),
        ("get_mode",),
    ]


@pytest.mark.parametrize(
    ("kill_switch_enabled", "expected_wan_fallback_enabled"),
    [(True, False), (False, True)],
)
def test_set_appliance_kill_switch_inverts_fallback_policy(
    kill_switch_enabled, expected_wan_fallback_enabled
):
    service, controller = make_service()
    calls = []

    def setter(enabled):
        calls.append(enabled)
        return {
            "kill_switch_enabled": not enabled,
            "wan_fallback_active": False,
        }

    controller.set_wan_fallback_enabled = setter

    result = service.set_appliance_kill_switch(kill_switch_enabled)

    assert calls == [expected_wan_fallback_enabled]
    assert result["kill_switch_enabled"] is kill_switch_enabled
    assert result["wan_fallback_active"] is False


def test_set_appliance_kill_switch_fails_when_controller_has_no_setter():
    service, _controller = make_service()

    with pytest.raises(RuntimeError, match="not available"):
        service.set_appliance_kill_switch(True)
