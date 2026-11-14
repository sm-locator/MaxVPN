from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.vless import (
    export_profiles_for_appliance,
    get_appliance_sync_status,
    get_runtime,
    prepare_runtime,
    set_appliance_kill_switch,
    start_runtime,
    stop_runtime,
    synchronize_from_appliance,
)
from app.schemas.vless import (
    VlessApplianceKillSwitchUpdateRequest,
    VlessApplianceSyncRequest,
)


class FakeRuntimeService:
    def __init__(self):
        self.calls = []

    def status(self, user_id=None):
        self.calls.append(("status", user_id))
        return {
            "installed": True,
            "running": False,
            "interface": "maxvpn0",
            "lan_routing_enabled": False,
            "message": "Runtime status only; LAN routes not configured",
        }

    def prepare(self, user_id):
        self.calls.append(("prepare", user_id))
        return {
            **self.status(),
            "action": "prepared",
            "prepared": True,
        }

    def start(self, user_id):
        self.calls.append(("start", user_id))
        return {
            **self.status(),
            "running": True,
            "action": "started",
            "prepared": True,
        }

    def stop(self, user_id=None):
        self.calls.append(("stop", user_id))
        return {
            **self.status(),
            "running": False,
            "action": "stopped",
            "prepared": True,
        }

    def appliance_sync_status(self, user_id):
        self.calls.append(("appliance_sync_status", user_id))
        return {"connected": True, "sync_required": False, "selection_mode": "auto"}

    def synchronize_from_appliance(self, user_id, *, confirm_delete_local_only=False):
        self.calls.append(
            ("synchronize_from_appliance", user_id, confirm_delete_local_only)
        )
        return {
            "connected": True,
            "sync_required": False,
            "selection_mode": "auto",
            "synced": True,
            "sync_result": {"imported": 1, "updated": 0, "deleted": 0},
        }

    def set_appliance_kill_switch(self, enabled):
        self.calls.append(("set_appliance_kill_switch", enabled))
        return {
            "kill_switch_enabled": enabled,
            "wan_fallback_active": False,
        }


@pytest.fixture
def user():
    return SimpleNamespace(id=7)


def test_get_runtime_reports_tun_but_not_lan_routing(user):
    service = FakeRuntimeService()

    result = get_runtime(current_user=user, service=service)

    assert result.interface == "maxvpn0"
    assert result.installed is True
    assert result.running is False
    assert result.lan_routing_enabled is False
    assert ("status", 7) in service.calls


def test_prepare_runtime_uses_authenticated_user_id(user):
    service = FakeRuntimeService()

    result = prepare_runtime(current_user=user, service=service)

    assert result.action == "prepared"
    assert result.prepared is True
    assert ("prepare", 7) in service.calls
    assert result.lan_routing_enabled is False


def test_start_runtime_uses_authenticated_user_id(user):
    service = FakeRuntimeService()

    result = start_runtime(current_user=user, service=service)

    assert result.action == "started"
    assert result.running is True
    assert result.lan_routing_enabled is False
    assert ("start", 7) in service.calls


def test_stop_runtime_calls_runtime_service(user):
    service = FakeRuntimeService()

    result = stop_runtime(current_user=user, service=service)

    assert result.action == "stopped"
    assert result.running is False
    assert ("stop", 7) in service.calls


def test_prepare_runtime_maps_missing_profile_to_404(user):
    service = FakeRuntimeService()

    def missing_profile(user_id):
        raise LookupError("vless_profile_not_found")

    service.prepare = missing_profile

    with pytest.raises(HTTPException) as exc_info:
        prepare_runtime(current_user=user, service=service)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "vless_profile_not_found"


class FakeExportService:
    def __init__(self):
        self.user_id = None

    def export_bundle(self, user_id):
        self.user_id = user_id
        return {
            "format": "maxvpn-vless-profiles",
            "version": 1,
            "profiles": [
                {"id": 1, "name": "Node", "enabled": True, "source": "vless://secret"}
            ],
            "settings": {"urltest_interval": "3m", "urltest_tolerance_ms": 50},
            "warning": "Keep this file private",
        }


def test_export_profiles_for_appliance_uses_authenticated_user(user):
    service = FakeExportService()

    result = export_profiles_for_appliance(current_user=user, service=service)

    assert result["format"] == "maxvpn-vless-profiles"
    assert result["profiles"][0]["source"].startswith("vless://")
    assert service.user_id == 7


def test_get_appliance_sync_status_uses_authenticated_user(user):
    service = FakeRuntimeService()

    result = get_appliance_sync_status(current_user=user, service=service)

    assert result["connected"] is True
    assert result["sync_required"] is False
    assert ("appliance_sync_status", 7) in service.calls


def test_synchronize_from_appliance_uses_authenticated_user(user):
    service = FakeRuntimeService()

    result = synchronize_from_appliance(
        data=VlessApplianceSyncRequest(confirm_delete_local_only=True),
        current_user=user,
        service=service,
    )

    assert result["synced"] is True
    assert result["sync_result"]["imported"] == 1
    assert ("synchronize_from_appliance", 7, True) in service.calls


def test_set_appliance_kill_switch_uses_authenticated_request(user):
    service = FakeRuntimeService()

    result = set_appliance_kill_switch(
        data=VlessApplianceKillSwitchUpdateRequest(enabled=True),
        current_user=user,
        service=service,
    )

    assert result == {
        "kill_switch_enabled": True,
        "wan_fallback_active": False,
    }
    assert ("set_appliance_kill_switch", True) in service.calls


def test_set_appliance_kill_switch_maps_router_error_to_502(user):
    service = FakeRuntimeService()

    def fail(_enabled):
        raise RuntimeError("router unreachable")

    service.set_appliance_kill_switch = fail

    with pytest.raises(HTTPException) as exc_info:
        set_appliance_kill_switch(
            data=VlessApplianceKillSwitchUpdateRequest(enabled=False),
            current_user=user,
            service=service,
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "router unreachable"
