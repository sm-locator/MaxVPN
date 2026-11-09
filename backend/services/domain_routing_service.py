from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Address, ip_address

from backend.models.traffic_routing_policy import (
    TrafficRoutingDecision,
    TrafficRoutingPolicy,
)
from backend.models.traffic_routing_rule import TrafficRoute
from backend.services.domain_routing_resolver import DomainRoutingResolver
from backend.services.traffic_routing_evaluator import TrafficRoutingEvaluator


@dataclass(frozen=True, slots=True)
class DomainRoutingResult:
    domain: str
    decision: TrafficRoutingDecision
    ipv4_addresses: tuple[str, ...]


class DomainRoutingService:
    """
    Resolves a domain only after the policy engine has determined
    its effective routing action.

    DIRECT:
        DNS A/AAAA records are resolved and IPv4 addresses are returned.

    VPN:
        No direct IPs are produced because VPN remains the default path.
    """

    def __init__(
        self,
        resolver: DomainRoutingResolver | None = None,
        evaluator: TrafficRoutingEvaluator | None = None,
    ) -> None:
        self._resolver = resolver or DomainRoutingResolver()
        self._evaluator = evaluator or TrafficRoutingEvaluator()

    def resolve(
        self,
        policy: TrafficRoutingPolicy,
        domain: str,
    ) -> DomainRoutingResult:
        decision = self._evaluator.decide_domain(policy, domain)

        if decision.action is not TrafficRoute.DIRECT:
            return DomainRoutingResult(
                domain=self._normalize_domain(domain),
                decision=decision,
                ipv4_addresses=(),
            )

        addresses = self._resolver.resolve(domain)

        ipv4_addresses = tuple(
            sorted(
                {
                    str(address)
                    for address in (ip_address(value) for value in addresses)
                    if isinstance(address, IPv4Address)
                }
            )
        )

        return DomainRoutingResult(
            domain=self._normalize_domain(domain),
            decision=decision,
            ipv4_addresses=ipv4_addresses,
        )

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        value = domain.strip().lower().rstrip(".")

        if value.startswith("*."):
            value = value[2:]

        return value
