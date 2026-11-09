from __future__ import annotations

from backend.models.traffic_routing_policy import (
    TrafficRoutingDecision,
    TrafficRoutingPolicy,
)
from backend.models.traffic_routing_rule import (
    TrafficRoutingRule,
)


class TrafficRoutingEvaluator:
    """
    Evaluates destination traffic against the MaxVPN smart-routing policy.
    """

    def decide_domain(
        self,
        policy: TrafficRoutingPolicy,
        domain: str,
    ) -> TrafficRoutingDecision:
        for rule in self._ordered_rules(policy):
            if rule.matches_domain(domain):
                return TrafficRoutingDecision(
                    action=rule.action,
                    rule=rule,
                )

        return TrafficRoutingDecision(
            action=policy.default_action,
        )

    def decide_ip(
        self,
        policy: TrafficRoutingPolicy,
        address: str,
    ) -> TrafficRoutingDecision:
        for rule in self._ordered_rules(policy):
            if rule.matches_ip(address):
                return TrafficRoutingDecision(
                    action=rule.action,
                    rule=rule,
                )

        return TrafficRoutingDecision(
            action=policy.default_action,
        )

    def effective_direct_ipv4_networks(
        self,
        policy: TrafficRoutingPolicy,
    ) -> tuple[str, ...]:
        """
        Return the effective IPv4 DIRECT networks after applying
        higher-priority VPN CIDR rules.

        Rules are evaluated from highest priority to lowest priority.
        A VPN rule claims its network, so lower-priority DIRECT rules
        cannot route that address space directly.
        """
        from ipaddress import IPv4Network

        blocked: list[IPv4Network] = []
        effective: list[IPv4Network] = []

        for rule in self._ordered_rules(policy):
            if rule.target_type.value != "cidr":
                continue

            if rule.address_family.value == "ipv6":
                continue

            network = IPv4Network(rule.target, strict=False)

            if rule.action.value == "vpn":
                blocked.append(network)
                continue

            remaining = [network]

            for blocked_network in blocked:
                next_remaining: list[IPv4Network] = []

                for candidate in remaining:
                    if not candidate.overlaps(blocked_network):
                        next_remaining.append(candidate)
                    elif candidate.subnet_of(blocked_network):
                        continue
                    elif blocked_network.subnet_of(candidate):
                        next_remaining.extend(
                            candidate.address_exclude(blocked_network)
                        )
                    else:
                        raise RuntimeError(
                            "Unexpected partially overlapping IPv4 networks"
                        )

                remaining = next_remaining

                if not remaining:
                    break

            effective.extend(remaining)

        return tuple(str(network) for network in effective)

    @staticmethod
    def _ordered_rules(
        policy: TrafficRoutingPolicy,
    ) -> tuple[TrafficRoutingRule, ...]:
        return tuple(
            sorted(
                (rule for rule in policy.rules if rule.enabled),
                key=lambda rule: rule.priority,
                reverse=True,
            )
        )
