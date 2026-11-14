from __future__ import annotations

from dataclasses import dataclass

from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.models.traffic_routing_rule import (
    TrafficRoute,
    TrafficTargetType,
)


class DomainRoutingCompileError(ValueError):
    """Raised when domain rules cannot be represented safely by dnsmasq."""


@dataclass(frozen=True, slots=True)
class DomainRoutingRuntimeConfig:
    direct_domains: tuple[str, ...]


class DomainRoutingRuntimeCompiler:
    """
    Compiles DOMAIN rules into the representation supported by the current
    dnsmasq integration.

    The current runtime can express:
        domain -> DIRECT

    VPN remains the default route.

    Conflicting DIRECT/VPN domain hierarchies are rejected because the
    dnsmasq ipset mapping is suffix-based and cannot represent exceptions
    such as:

        example.com     -> DIRECT
        api.example.com -> VPN
    """

    def compile(
        self,
        policy: TrafficRoutingPolicy,
    ) -> DomainRoutingRuntimeConfig:
        domain_rules = tuple(
            rule
            for rule in policy.rules
            if (rule.enabled and rule.target_type is TrafficTargetType.DOMAIN)
        )

        self._validate_compatible_domain_rules(domain_rules)

        direct_domains = tuple(
            rule.target
            for rule in sorted(
                (rule for rule in domain_rules if rule.action is TrafficRoute.DIRECT),
                key=lambda rule: rule.priority,
                reverse=True,
            )
        )

        return DomainRoutingRuntimeConfig(
            direct_domains=direct_domains,
        )

    @staticmethod
    def _validate_compatible_domain_rules(rules: tuple) -> None:
        for index, first in enumerate(rules):
            for second in rules[index + 1 :]:
                if first.action is second.action:
                    continue

                if DomainRoutingRuntimeCompiler._domains_overlap(
                    first.target,
                    second.target,
                ):
                    raise DomainRoutingCompileError(
                        "conflicting domain routing rules cannot be represented "
                        f"safely by dnsmasq: {first.target!r} "
                        f"({first.action.value}, priority={first.priority}) "
                        f"and {second.target!r} "
                        f"({second.action.value}, priority={second.priority})"
                    )

    @staticmethod
    def _domains_overlap(first: str, second: str) -> bool:
        first = first.lower().rstrip(".")
        second = second.lower().rstrip(".")

        return (
            first == second
            or first.endswith(f".{second}")
            or second.endswith(f".{first}")
        )
