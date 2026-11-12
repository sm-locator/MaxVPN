from unittest.mock import Mock

import pytest
from backend.services.smart_routing_sync import (
    SmartRoutingSyncError,
    SmartRoutingSyncService,
)
from fastapi.testclient import TestClient

from app.api.v1.smart_routing_sync import get_sync_service
from app.auth.dependencies import get_current_user
from app.main import app
from app.models.user import User

client = TestClient(app)


def make_user() -> User:
    return User(
        id=42,
        email="user@example.com",
        password_hash="hash",
        role="admin",
    )


def make_runtime() -> dict:
    return dict(
        direct_ipset=True,
        static_ipset=True,
        static_net_ipset=True,
        mangle_direct_count=1,
        mangle_static_count=1,
        mangle_static_net_count=1,
        ip_rule="100: from all fwmark 0x64/0xff lookup 200",
        table_200="default via 198.18.0.1 dev eth1",
        config_hash="snapshot",
        applied_config_hash="snapshot",
    )


def test_apply_uses_saved_appliance_snapshot() -> None:
    current_user = make_user()
    service = Mock(spec=SmartRoutingSyncService)
    service.apply_remote_runtime.return_value = make_runtime()

    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_sync_service] = lambda: service

    try:
        response = client.post(
            "/api/v1/smart-routing/apply",
            json={"expected_remote_fingerprint": "reviewed-snapshot"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["healthy"] is True
    service.apply_remote_runtime.assert_called_once_with("reviewed-snapshot")


def test_apply_requires_authentication() -> None:
    response = client.post(
        "/api/v1/smart-routing/apply",
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "error,code", [("remote_state_changed", 409), ("brume_routing_apply_failed", 502)]
)
def test_apply_maps_appliance_errors(error, code) -> None:
    current_user = make_user()
    service = Mock(spec=SmartRoutingSyncService)
    service.apply_remote_runtime.side_effect = SmartRoutingSyncError(error)

    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_sync_service] = lambda: service

    try:
        response = client.post(
            "/api/v1/smart-routing/apply",
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == code
    assert response.json() == {"detail": error}


@pytest.mark.parametrize(
    "broken",
    [
        dict(mangle_static_count=2),
        dict(ip_rule=""),
        dict(applied_config_hash="old"),
        dict(static_net_ipset=False),
    ],
)
def test_apply_does_not_report_unverified_runtime_as_success(broken):
    service = Mock(spec=SmartRoutingSyncService)
    service.apply_remote_runtime.return_value = make_runtime() | broken
    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_sync_service] = lambda: service
    try:
        response = client.post("/api/v1/smart-routing/apply")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 502


def make_runtime_plan() -> Mock:
    plan = Mock()
    plan.has_changes = True
    plan.current.direct_ipv4_addresses = ("192.0.2.10",)
    plan.current.direct_domains = ("old.example",)
    plan.current.rendered_domains = ("old.example",)
    plan.current.policy_rules = ("100: from all fwmark 0x64/0xff lookup 200",)
    plan.current.routing_table_200 = ("default via 46.48.56.1 dev eth1",)

    plan.desired.direct_ipv4_networks = ("192.0.2.0/24",)
    plan.desired.direct_domains = ("example.com",)

    plan.diff.current_ipv4_addresses = ("192.0.2.10",)
    plan.diff.desired_ipv4_networks = ("192.0.2.0/24",)
    plan.diff.covered_ipv4_addresses = ("192.0.2.10",)
    plan.diff.stale_ipv4_addresses = ()
    plan.diff.ipv4_replace_required = False
    plan.diff.added_domains = ("example.com",)
    plan.diff.removed_domains = ("old.example",)
    plan.diff.unchanged_domains = ()

    plan.render.return_value = "SMART ROUTING RUNTIME DIFF\nRESULT: CHANGES REQUIRED"

    return plan


def test_runtime_preview_uses_current_user_id() -> None:
    from backend.application.use_cases.preview_smart_routing_runtime import (
        PreviewSmartRoutingRuntimeUseCase,
    )

    from app.api.v1.smart_routing_apply import (
        get_preview_smart_routing_runtime_use_case,
    )

    current_user = make_user()
    use_case = Mock(spec=PreviewSmartRoutingRuntimeUseCase)
    plan = make_runtime_plan()

    use_case.execute_for_user.return_value = plan

    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_preview_smart_routing_runtime_use_case] = lambda: (
        use_case
    )

    try:
        response = client.get(
            "/api/v1/smart-routing/runtime-preview",
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    body = response.json()

    assert body["has_changes"] is True
    assert body["current"]["direct_ipv4_addresses"] == ["192.0.2.10"]
    assert body["current"]["direct_domains"] == ["old.example"]
    assert body["desired"]["direct_ipv4_networks"] == ["192.0.2.0/24"]
    assert body["desired"]["direct_domains"] == ["example.com"]
    assert body["diff"]["added_domains"] == ["example.com"]
    assert body["diff"]["removed_domains"] == ["old.example"]
    assert body["rendered"] == ("SMART ROUTING RUNTIME DIFF\nRESULT: CHANGES REQUIRED")

    use_case.execute_for_user.assert_called_once_with(42)


def test_runtime_preview_requires_authentication() -> None:
    response = client.get(
        "/api/v1/smart-routing/runtime-preview",
    )

    assert response.status_code == 401
