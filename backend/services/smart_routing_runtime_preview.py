from __future__ import annotations

from dataclasses import dataclass

from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.services.domain_routing_runtime_compiler import (
    DomainRoutingRuntimeCompiler,
)
from backend.services.traffic_routing_evaluator import TrafficRoutingEvaluator


@dataclass(frozen=True, slots=True)
class SmartRoutingRuntimePreview:
    direct_ipv4_networks: tuple[str, ...]
    direct_domains: tuple[str, ...]


class SmartRoutingRuntimePreviewService:
    """
    Builds a read-only representation of the desired Smart Routing runtime.

    Static IPv4/CIDR destinations belong to the MAXVPN_DIRECT ipset.
    Domain destinations belong to dnsmasq mappings and are intentionally
    kept separate because dnsmasq resolves their current IP addresses.
    """

    def __init__(
        self,
        evaluator: TrafficRoutingEvaluator | None = None,
        domain_compiler: DomainRoutingRuntimeCompiler | None = None,
    ) -> None:
        self._evaluator = evaluator or TrafficRoutingEvaluator()
        self._domain_compiler = domain_compiler or DomainRoutingRuntimeCompiler()

    def build(
        self,
        policy: TrafficRoutingPolicy,
    ) -> SmartRoutingRuntimePreview:
        direct_networks = self._evaluator.effective_direct_ipv4_networks(
            policy,
        )

        domain_config = self._domain_compiler.compile(policy)

        return SmartRoutingRuntimePreview(
            direct_ipv4_networks=tuple(sorted(direct_networks)),
            direct_domains=tuple(sorted(domain_config.direct_domains)),
        )
