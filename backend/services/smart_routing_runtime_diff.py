from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address, ip_network

from backend.services.smart_routing_runtime_preview import (
    SmartRoutingRuntimePreview,
)
from backend.services.smart_routing_runtime_state import (
    SmartRoutingRuntimeState,
)


@dataclass(frozen=True, slots=True)
class SmartRoutingRuntimeDiff:
    current_ipv4_addresses: tuple[str, ...]
    desired_ipv4_networks: tuple[str, ...]
    covered_ipv4_addresses: tuple[str, ...]
    stale_ipv4_addresses: tuple[str, ...]
    ipv4_replace_required: bool
    added_domains: tuple[str, ...]
    removed_domains: tuple[str, ...]
    unchanged_domains: tuple[str, ...]

    @property
    def has_changes(self) -> bool:
        return self.ipv4_replace_required or bool(
            self.added_domains or self.removed_domains
        )


class SmartRoutingRuntimeDiffService:
    """
    Compares actual Smart Routing runtime state with desired state.

    IPv4 runtime uses a hash:ip ipset while policy/preview uses CIDR
    networks. Therefore IPv4 is compared semantically by checking whether
    current IP members are covered by desired networks and whether each
    desired network is represented by at least one current member.
    """

    def build(
        self,
        current: SmartRoutingRuntimeState,
        desired: SmartRoutingRuntimePreview,
    ) -> SmartRoutingRuntimeDiff:
        current_ipv4 = tuple(sorted(set(current.direct_ipv4_addresses)))
        static_current_ipv4 = tuple(sorted(set(current.static_direct_ipv4_addresses)))
        desired_networks = tuple(sorted(set(desired.direct_ipv4_networks)))

        networks = tuple(
            ip_network(network, strict=False) for network in desired_networks
        )

        covered = tuple(
            value
            for value in static_current_ipv4
            if any(ip_address(value) in network for network in networks)
        )

        stale = tuple(
            value
            for value in static_current_ipv4
            if not any(ip_address(value) in network for network in networks)
        )

        desired_has_unrepresented_network = any(
            not any(ip_address(value) in network for value in static_current_ipv4)
            for network in networks
        )

        ipv4_replace_required = bool(
            stale
            or (not static_current_ipv4 and networks)
            or desired_has_unrepresented_network
        )

        current_domains = set(current.direct_domains)
        desired_domains = set(desired.direct_domains)

        added_domains = tuple(sorted(desired_domains - current_domains))
        removed_domains = tuple(sorted(current_domains - desired_domains))
        unchanged_domains = tuple(sorted(current_domains & desired_domains))

        return SmartRoutingRuntimeDiff(
            current_ipv4_addresses=current_ipv4,
            desired_ipv4_networks=desired_networks,
            covered_ipv4_addresses=tuple(sorted(covered)),
            stale_ipv4_addresses=tuple(sorted(stale)),
            ipv4_replace_required=ipv4_replace_required,
            added_domains=added_domains,
            removed_domains=removed_domains,
            unchanged_domains=unchanged_domains,
        )
