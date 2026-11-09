from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import get_current_user
from app.models.user import User
from backend.application.container import (
    build_smart_routing_domain_diagnostic_service,
)
from backend.services.smart_routing_domain_diagnostic import (
    SmartRoutingDomainDiagnosticService,
)

router = APIRouter(
    prefix="/smart-routing",
    tags=["Smart Routing"],
)


def get_smart_routing_domain_diagnostic_service() -> (
    SmartRoutingDomainDiagnosticService
):
    return build_smart_routing_domain_diagnostic_service()


@router.get("/domain-diagnostic")
def smart_routing_domain_diagnostic(
    domain: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
    service: SmartRoutingDomainDiagnosticService = Depends(
        get_smart_routing_domain_diagnostic_service,
    ),
) -> dict[str, object]:
    del current_user
    result = service.check(domain)

    return {
        "domain": result.domain,
        "dns_ipv4_addresses": result.dns_ipv4_addresses,
        "present_ipv4_addresses": result.present_ipv4_addresses,
        "missing_ipv4_addresses": result.missing_ipv4_addresses,
        "stale_ipv4_addresses": result.stale_ipv4_addresses,
        "route_results": result.route_results,
        "healthy": result.healthy,
        "reason": result.reason,
        "checks": {
            "direct_ipset_readable": result.direct_ipset_readable,
            "dnsmasq_mapping_present": result.dnsmasq_mapping_present,
            "marking_rule_present": result.marking_rule_present,
            "policy_rule_present": result.policy_rule_present,
            "forward_chain_attached": result.forward_chain_attached,
            "direct_forward_rule_present": result.direct_forward_rule_present,
            "nat_chain_attached": result.nat_chain_attached,
            "nat_masquerade_rule_present": result.nat_masquerade_rule_present,
        },
    }
