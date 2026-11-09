from unittest.mock import Mock

from backend.application.use_cases.apply_smart_routing import (
    ApplySmartRoutingUseCase,
)
from backend.infrastructure.openwrt.openwrt_traffic_routing import (
    OpenWrtTrafficRoutingResult,
)
from backend.services.smart_routing_service import (
    SmartRoutingRuntimeCapabilityError,
)
from fastapi.testclient import TestClient

from app.api.v1.smart_routing_apply import get_apply_use_case
from app.auth.dependencies import get_current_user
from app.main import app
from app.models.user import User

client = TestClient(app)


def make_user() -> User:
    return User(
        id=42,
        email="user@example.com",
        password_hash="hash",
        role="user",
    )


def make_result() -> OpenWrtTrafficRoutingResult:
    return OpenWrtTrafficRoutingResult(
        healthy=True,
        direct_ipset_exists=True,
        direct_rule_count=2,
        routing_table_exists=True,
        direct_route_exists=True,
    )


def test_apply_uses_current_user_id() -> None:
    current_user = make_user()
    use_case = Mock(spec=ApplySmartRoutingUseCase)
    use_case.execute_for_user.return_value = make_result()

    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_apply_use_case] = lambda: use_case

    try:
        response = client.post(
            "/api/v1/smart-routing/apply",
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["healthy"] is True
    use_case.execute_for_user.assert_called_once_with(42)


def test_apply_requires_authentication() -> None:
    response = client.post(
        "/api/v1/smart-routing/apply",
    )

    assert response.status_code == 401


def test_apply_maps_runtime_capability_error_to_422() -> None:
    current_user = make_user()
    use_case = Mock(spec=ApplySmartRoutingUseCase)
    use_case.execute_for_user.side_effect = SmartRoutingRuntimeCapabilityError(
        "smart_routing_runtime_capability_error: domain targets are not supported"
    )

    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_apply_use_case] = lambda: use_case

    try:
        response = client.post(
            "/api/v1/smart-routing/apply",
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "smart_routing_runtime_capability_error: domain targets are not supported"
        ),
    }


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
