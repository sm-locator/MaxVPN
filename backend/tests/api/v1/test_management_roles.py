from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.api.v1.smart_routing_apply import get_smart_routing_service
from app.api.v1.smart_routing_dependency_diagnostic import (
    get_runtime_executor,
    get_session_service,
)
from app.api.v1.smart_routing_domain_diagnostic import (
    get_smart_routing_domain_diagnostic_service,
)
from app.api.v1.smart_routing_sync import get_sync_service
from app.api.v1.vless import get_vless_runtime_service
from app.api.v1.vpn import get_vpn_profile_service, get_vpn_runtime_service
from app.auth.dependencies import get_current_user
from app.main import app
from app.models.user import User

OPERATIONS = [
    ("POST", "/vpn/start"),
    ("POST", "/vpn/stop"),
    ("POST", "/vpn/mode"),
    ("POST", "/vpn/profile/apply"),
    ("POST", "/vpn/profile/import-current-runtime"),
    ("POST", "/vless/runtime/prepare"),
    ("POST", "/vless/runtime/start"),
    ("POST", "/vless/runtime/stop"),
    ("POST", "/vless/runtime/select"),
    ("GET", "/vless/appliance-sync/status"),
    ("POST", "/vless/appliance-sync"),
    ("PUT", "/vless/appliance/kill-switch"),
    ("GET", "/vless/runtime/selection-history"),
    ("GET", "/vless/profiles/delays"),
    ("POST", "/smart-routing/apply"),
    ("GET", "/smart-routing/runtime-preview"),
    ("GET", "/smart-routing/sync"),
    ("POST", "/smart-routing/sync/push"),
    ("POST", "/smart-routing/sync/pull"),
    ("POST", "/smart-routing/sync/enabled-from-brume"),
    ("GET", "/smart-routing/domain-diagnostic?domain=example.test"),
    ("POST", "/smart-routing/dependency-diagnostic/start"),
    ("GET", "/smart-routing/dependency-diagnostic/secret-token"),
    ("POST", "/smart-routing/dependency-diagnostic/secret-token/rules"),
]


@pytest.mark.parametrize("method,path", OPERATIONS)
@pytest.mark.parametrize("authenticated", [False, True])
def test_shared_router_operations_reject_before_constructing_services(
    method, path, authenticated
):
    factories = [
        get_smart_routing_service,
        get_sync_service,
        get_session_service,
        get_runtime_executor,
        get_smart_routing_domain_diagnostic_service,
        get_vpn_runtime_service,
        get_vpn_profile_service,
        get_vless_runtime_service,
    ]
    spies = [Mock() for _ in factories]
    for dependency, spy in zip(factories, spies):
        app.dependency_overrides[dependency] = lambda spy=spy: spy()
    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: User(
            id=42, email="user@example.test", password_hash="hash", role="user"
        )
    try:
        response = TestClient(app).request(method, "/api/v1" + path, json={})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == (403 if authenticated else 401), response.text
    for spy in spies:
        spy.assert_not_called()
