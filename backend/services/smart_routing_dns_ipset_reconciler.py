from __future__ import annotations

from dataclasses import dataclass

from backend.services.smart_routing_dns_domain_state import (
    SmartRoutingDnsDomainStateStore,
)


@dataclass(frozen=True, slots=True)
class SmartRoutingDnsIpSetReconciliation:
    active_ipv4_addresses: tuple[str, ...]
    current_ipv4_addresses: tuple[str, ...]
    addresses_to_add: tuple[str, ...]
    addresses_to_remove: tuple[str, ...]
    active_ipv6_addresses: tuple[str, ...] = ()
    current_ipv6_addresses: tuple[str, ...] = ()
    ipv6_addresses_to_add: tuple[str, ...] = ()
    ipv6_addresses_to_remove: tuple[str, ...] = ()


class SmartRoutingDnsIpSetReconciler:
    """
    Calculates the safe difference between DNS-derived DIRECT state
    and the current MAXVPN_DIRECT ipset.

    MAXVPN_DIRECT_STATIC is intentionally outside this component.
    """

    def build(
        self,
        store: SmartRoutingDnsDomainStateStore,
        current_ipv4_addresses: tuple[str, ...],
        current_ipv6_addresses: tuple[str, ...] = (),
    ) -> SmartRoutingDnsIpSetReconciliation:
        active_ipv4 = set(store.all_ipv4_addresses())
        current_ipv4 = set(current_ipv4_addresses)

        active_ipv6 = set(store.all_ipv6_addresses())
        current_ipv6 = set(current_ipv6_addresses)

        return SmartRoutingDnsIpSetReconciliation(
            active_ipv4_addresses=tuple(sorted(active_ipv4)),
            current_ipv4_addresses=tuple(sorted(current_ipv4)),
            addresses_to_add=tuple(sorted(active_ipv4 - current_ipv4)),
            addresses_to_remove=tuple(sorted(current_ipv4 - active_ipv4)),
            active_ipv6_addresses=tuple(sorted(active_ipv6)),
            current_ipv6_addresses=tuple(sorted(current_ipv6)),
            ipv6_addresses_to_add=tuple(sorted(active_ipv6 - current_ipv6)),
            ipv6_addresses_to_remove=tuple(sorted(current_ipv6 - active_ipv6)),
        )
