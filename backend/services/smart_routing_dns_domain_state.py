from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SmartRoutingDnsDomainState:
    domain: str
    ipv4_addresses: tuple[str, ...]
    ipv6_addresses: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SmartRoutingDnsStateUpdate:
    domain: str
    previous_ipv4_addresses: tuple[str, ...]
    current_ipv4_addresses: tuple[str, ...]
    added_ipv4_addresses: tuple[str, ...]
    removed_ipv4_addresses: tuple[str, ...]
    changed: bool
    previous_ipv6_addresses: tuple[str, ...] = ()
    current_ipv6_addresses: tuple[str, ...] = ()
    added_ipv6_addresses: tuple[str, ...] = ()
    removed_ipv6_addresses: tuple[str, ...] = ()


class SmartRoutingDnsDomainStateStore:
    """
    In-memory state of successful DNS A/AAAA responses per DIRECT domain.

    IPv4 and IPv6 state are deliberately tracked independently so that
    refreshing one family does not erase the other family's addresses.

    The store deliberately contains no OpenWrt/ipset logic.
    """

    def __init__(self) -> None:
        self._states: dict[
            str,
            tuple[tuple[str, ...], tuple[str, ...]],
        ] = {}

    def get(self, domain: str) -> SmartRoutingDnsDomainState | None:
        normalized_domain = self._normalize_domain(domain)
        state = self._states.get(normalized_domain)

        if state is None:
            return None

        ipv4_addresses, ipv6_addresses = state

        return SmartRoutingDnsDomainState(
            domain=normalized_domain,
            ipv4_addresses=ipv4_addresses,
            ipv6_addresses=ipv6_addresses,
        )

    def update(
        self,
        domain: str,
        ipv4_addresses: tuple[str, ...] | None = None,
        ipv6_addresses: tuple[str, ...] | None = None,
    ) -> SmartRoutingDnsStateUpdate:
        normalized_domain = self._normalize_domain(domain)
        previous_ipv4, previous_ipv6 = self._states.get(
            normalized_domain,
            ((), ()),
        )

        current_ipv4 = (
            previous_ipv4
            if ipv4_addresses is None
            else tuple(sorted(set(ipv4_addresses)))
        )
        current_ipv6 = (
            previous_ipv6
            if ipv6_addresses is None
            else tuple(sorted(set(ipv6_addresses)))
        )

        previous_ipv4_set = set(previous_ipv4)
        current_ipv4_set = set(current_ipv4)
        previous_ipv6_set = set(previous_ipv6)
        current_ipv6_set = set(current_ipv6)

        added_ipv4 = tuple(sorted(current_ipv4_set - previous_ipv4_set))
        removed_ipv4 = tuple(sorted(previous_ipv4_set - current_ipv4_set))
        added_ipv6 = tuple(sorted(current_ipv6_set - previous_ipv6_set))
        removed_ipv6 = tuple(sorted(previous_ipv6_set - current_ipv6_set))

        self._states[normalized_domain] = (
            current_ipv4,
            current_ipv6,
        )

        changed = current_ipv4 != previous_ipv4 or current_ipv6 != previous_ipv6

        return SmartRoutingDnsStateUpdate(
            domain=normalized_domain,
            previous_ipv4_addresses=previous_ipv4,
            current_ipv4_addresses=current_ipv4,
            added_ipv4_addresses=added_ipv4,
            removed_ipv4_addresses=removed_ipv4,
            changed=changed,
            previous_ipv6_addresses=previous_ipv6,
            current_ipv6_addresses=current_ipv6,
            added_ipv6_addresses=added_ipv6,
            removed_ipv6_addresses=removed_ipv6,
        )

    def remove(self, domain: str) -> SmartRoutingDnsStateUpdate | None:
        normalized_domain = self._normalize_domain(domain)
        previous = self._states.pop(normalized_domain, None)

        if previous is None:
            return None

        previous_ipv4, previous_ipv6 = previous

        return SmartRoutingDnsStateUpdate(
            domain=normalized_domain,
            previous_ipv4_addresses=previous_ipv4,
            current_ipv4_addresses=(),
            added_ipv4_addresses=(),
            removed_ipv4_addresses=previous_ipv4,
            changed=True,
            previous_ipv6_addresses=previous_ipv6,
            current_ipv6_addresses=(),
            added_ipv6_addresses=(),
            removed_ipv6_addresses=previous_ipv6,
        )

    def prune_to_domains(
        self,
        direct_domains: tuple[str, ...] | list[str] | set[str],
    ) -> tuple[str, ...]:
        """
        Remove cached DNS states that are no longer covered by an active
        DIRECT domain and return IPv4 addresses that disappeared from the
        remaining state.

        IPv6 states are pruned at the same time; callers that need IPv6
        cleanup can compare all_ipv6_addresses() before and after pruning.

        A DIRECT domain also covers its subdomains, matching dnsmasq's
        domain -> ipset behavior.
        """
        allowed = tuple(
            sorted(
                {
                    self._normalize_domain(domain)
                    for domain in direct_domains
                    if self._normalize_domain(domain)
                }
            )
        )

        before = set(self.all_ipv4_addresses())

        for domain in tuple(self._states):
            if not any(
                domain == allowed_domain or domain.endswith("." + allowed_domain)
                for allowed_domain in allowed
            ):
                del self._states[domain]

        after = set(self.all_ipv4_addresses())
        return tuple(sorted(before - after))

    def replace_all(
        self,
        states: (
            tuple[SmartRoutingDnsDomainState, ...] | list[SmartRoutingDnsDomainState]
        ),
    ) -> None:
        """Replace the complete in-memory snapshot with normalized states."""
        replacement: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
        for state in states:
            domain = self._normalize_domain(state.domain)
            if not domain:
                continue
            replacement[domain] = (
                tuple(sorted(set(state.ipv4_addresses))),
                tuple(sorted(set(state.ipv6_addresses))),
            )
        self._states = replacement

    def clear(self) -> None:
        """Clear all per-domain state."""
        self._states.clear()

    def all_states(self) -> tuple[SmartRoutingDnsDomainState, ...]:
        return tuple(
            SmartRoutingDnsDomainState(
                domain=domain,
                ipv4_addresses=ipv4_addresses,
                ipv6_addresses=ipv6_addresses,
            )
            for domain, (ipv4_addresses, ipv6_addresses) in sorted(self._states.items())
        )

    def all_ipv4_addresses(self) -> tuple[str, ...]:
        addresses: set[str] = set()

        for ipv4_addresses, _ in self._states.values():
            addresses.update(ipv4_addresses)

        return tuple(sorted(addresses))

    def all_ipv6_addresses(self) -> tuple[str, ...]:
        addresses: set[str] = set()

        for _, ipv6_addresses in self._states.values():
            addresses.update(ipv6_addresses)

        return tuple(sorted(addresses))

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        return domain.strip().rstrip(".").lower()
