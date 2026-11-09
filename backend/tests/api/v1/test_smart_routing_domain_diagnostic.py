from unittest.mock import Mock

from backend.services.smart_routing_domain_diagnostic import (
    SmartRoutingDomainDiagnosticResult,
    SmartRoutingDomainDiagnosticService,
)
from fastapi.testclient import TestClient

from app.api.v1.smart_routing_domain_diagnostic import (
    get_smart_routing_domain_diagnostic_service,
)
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


def make_result() -> SmartRoutingDomainDiagnosticResult:
    return SmartRoutingDomainDiagnosticResult(
        domain="cian.ru",
        dns_ipv4_addresses=("51.250.123.126",),
        present_ipv4_addresses=("51.250.123.126",),
        missing_ipv4_addresses=(),
        stale_ipv4_addresses=(),
        route_results=(
            "51.250.123.126 via 46.48.56.1 dev eth1 "
            "table 200 src 46.48.56.64 mark 0x64 OK",
        ),
        healthy=True,
        reason=None,
        direct_ipset_readable=True,
        dnsmasq_mapping_present=True,
        marking_rule_present=True,
        policy_rule_present=True,
        forward_chain_attached=True,
        direct_forward_rule_present=True,
        nat_chain_attached=True,
        nat_masquerade_rule_present=True,
    )


def test_domain_diagnostic_uses_current_user_and_returns_result() -> None:
    current_user = make_user()
    service = Mock(spec=SmartRoutingDomainDiagnosticService)
    service.check.return_value = make_result()

    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_smart_routing_domain_diagnostic_service] = lambda: (
        service
    )

    try:
        response = client.get(
            "/api/v1/smart-routing/domain-diagnostic",
            params={"domain": "CIAN.RU."},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()

    assert body["domain"] == "cian.ru"
    assert body["dns_ipv4_addresses"] == ["51.250.123.126"]
    assert body["present_ipv4_addresses"] == ["51.250.123.126"]
    assert body["missing_ipv4_addresses"] == []
    assert body["healthy"] is True
    assert body["reason"] is None
    assert body["checks"] == {
        "direct_ipset_readable": True,
        "dnsmasq_mapping_present": True,
        "marking_rule_present": True,
        "policy_rule_present": True,
        "forward_chain_attached": True,
        "direct_forward_rule_present": True,
        "nat_chain_attached": True,
        "nat_masquerade_rule_present": True,
    }
    service.check.assert_called_once_with("CIAN.RU.")


def test_domain_diagnostic_requires_authentication() -> None:
    response = client.get(
        "/api/v1/smart-routing/domain-diagnostic",
        params={"domain": "cian.ru"},
    )
    assert response.status_code == 401
