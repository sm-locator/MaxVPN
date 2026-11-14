from __future__ import annotations

from dataclasses import dataclass

from backend.infrastructure.openwrt.openwrt_smart_routing_dns_cleanup import (
    OpenWrtSmartRoutingDnsCleanup,
)
from backend.services.smart_routing_dns_domain_state import (
    SmartRoutingDnsDomainStateStore,
)
from backend.services.smart_routing_dns_ipset_reconciler import (
    SmartRoutingDnsIpSetReconciler,
)
from backend.services.smart_routing_dns_log_reader import (
    SmartRoutingDnsLogCursor,
    SmartRoutingDnsLogReader,
)
from backend.services.smart_routing_dns_response_observer import (
    SmartRoutingDnsResponseObserver,
)


@dataclass(frozen=True, slots=True)
class SmartRoutingDnsCoordinatorResult:
    processed_responses: int
    added_ipv4_addresses: tuple[str, ...]
    removed_ipv4_addresses: tuple[str, ...]
    cursor: SmartRoutingDnsLogCursor
    log_reset: bool
    added_ipv6_addresses: tuple[str, ...] = ()
    removed_ipv6_addresses: tuple[str, ...] = ()


class SmartRoutingDnsReconciliationCoordinator:
    """
    Incrementally consumes dnsmasq DNS responses and reconciles
    MAXVPN_DIRECT with the current successful DIRECT-domain state.
    """

    def __init__(
        self,
        log_reader: SmartRoutingDnsLogReader,
        response_observer: SmartRoutingDnsResponseObserver,
        state_store: SmartRoutingDnsDomainStateStore,
        ipset_reconciler: SmartRoutingDnsIpSetReconciler,
        runtime_state,
        cleanup: OpenWrtSmartRoutingDnsCleanup,
        state_repository=None,
    ) -> None:
        self._log_reader = log_reader
        self._response_observer = response_observer
        self._state_store = state_store
        self._ipset_reconciler = ipset_reconciler
        self._runtime_state = runtime_state
        self._cleanup = cleanup
        self._state_repository = state_repository
        self._persistent_state_initialized = False

    @property
    def persistent_state_enabled(self) -> bool:
        return self._state_repository is not None

    def initialize_persistent_state(self) -> None:
        """Restore durable ownership and queue idempotent ADD repairs."""
        if self._state_repository is None or self._persistent_state_initialized:
            return

        states = self._state_repository.load_domain_states()
        self._state_store.replace_all(states)
        # Missing owned members are detected against the live ipsets by the
        # first post-bootstrap flush. Do not enqueue redundant ADDs for entries
        # that already exist on the router.
        self._persistent_state_initialized = True

    def flush_pending_ipset_operations(
        self,
        *,
        allow_deletions: bool = True,
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        """Apply durable desired ipset state; acknowledge only successful commands."""
        if self._state_repository is None:
            return (), (), (), ()
        if not self._persistent_state_initialized:
            raise RuntimeError("smart_routing_dns_persistence_not_initialized")

        runtime_state = self._runtime_state.collect()
        static_ipv4 = set(getattr(runtime_state, "static_direct_ipv4_addresses", ()))
        static_ipv6 = set(getattr(runtime_state, "static_direct_ipv6_addresses", ()))
        current_ipv4 = set(getattr(runtime_state, "direct_ipv4_addresses", ()))
        current_ipv6 = set(getattr(runtime_state, "direct_ipv6_addresses", ()))
        dynamic_ipv4 = current_ipv4 - static_ipv4

        # Repair missing members owned by active DIRECT domains. This is add-only:
        # unknown live members are never inferred to be stale.
        missing_ipv4 = tuple(
            sorted(
                set(self._state_store.all_ipv4_addresses()) - dynamic_ipv4 - static_ipv4
            )
        )
        missing_ipv6 = tuple(
            sorted(
                set(self._state_store.all_ipv6_addresses()) - current_ipv6 - static_ipv6
            )
        )
        self._state_repository.enqueue_present_addresses(missing_ipv4, missing_ipv6)

        added_ipv4: list[str] = []
        removed_ipv4: list[str] = []
        added_ipv6: list[str] = []
        removed_ipv6: list[str] = []

        for operation in self._state_repository.list_pending_operations():
            family = operation.address_family
            address = operation.address
            desired_present = operation.desired_present

            if not desired_present and not allow_deletions:
                continue

            if family == "ipv4":
                static_addresses = static_ipv4
                if address in static_addresses:
                    # A static rule already guarantees routing. Defer absence until
                    # the static rule is removed; a present intent can be acked
                    # because missing dynamic members are re-enqueued on each pass.
                    if desired_present:
                        self._state_repository.acknowledge_operation(operation)
                    continue
                if desired_present:
                    if address in dynamic_ipv4:
                        self._state_repository.acknowledge_operation(operation)
                        continue
                    applied = self._cleanup.add_addresses((address,))
                    added_ipv4.extend(applied)
                else:
                    applied = self._cleanup.remove_stale((address,))
                    removed_ipv4.extend(applied)
            elif family == "ipv6":
                if address in static_ipv6:
                    if desired_present:
                        self._state_repository.acknowledge_operation(operation)
                    continue
                if desired_present:
                    if address in current_ipv6:
                        self._state_repository.acknowledge_operation(operation)
                        continue
                    add_ipv6 = getattr(self._cleanup, "add_ipv6_addresses", None)
                    if add_ipv6 is None:
                        raise RuntimeError("smart_routing_dns_ipv6_cleanup_unsupported")
                    added_ipv6.extend(add_ipv6((address,)))
                else:
                    remove_ipv6 = getattr(self._cleanup, "remove_stale_ipv6", None)
                    if remove_ipv6 is None:
                        raise RuntimeError("smart_routing_dns_ipv6_cleanup_unsupported")
                    removed_ipv6.extend(remove_ipv6((address,)))
            else:
                raise RuntimeError(
                    f"smart_routing_dns_invalid_outbox_address_family: {family!r}"
                )

            # Conditional delete protects a newer intent written while the
            # remote command was in flight. A lost acknowledgement is safe:
            # ADD uses -exist and DELETE accepts an already-absent address.
            self._state_repository.acknowledge_operation(operation)

        return (
            tuple(added_ipv4),
            tuple(removed_ipv4),
            tuple(added_ipv6),
            tuple(removed_ipv6),
        )

    def current_cursor(self) -> SmartRoutingDnsLogCursor:
        """Return the current DNS log cursor without processing log entries."""
        return self._log_reader.current_cursor()

    def reset_state(self) -> None:
        """Reset partial DNS transactions without discarding durable ownership."""
        if self._state_repository is None:
            self._state_store.clear()
        self._response_observer.reset()

    def reconcile(
        self,
        *,
        direct_domains: tuple[str, ...],
        cursor: SmartRoutingDnsLogCursor | None = None,
        dry_run: bool = False,
        force_ipset_reconcile: bool = False,
        force_ipset_add_only: bool = False,
    ) -> SmartRoutingDnsCoordinatorResult:
        if self._state_repository is not None:
            return self._reconcile_persistent(
                direct_domains=direct_domains,
                cursor=cursor,
                dry_run=dry_run,
                force_ipset_reconcile=force_ipset_reconcile,
            )

        runtime_state = None
        if force_ipset_reconcile:
            # A forced full diff can delete entries not present in the
            # in-memory DNS ownership map. Re-read the authoritative policy
            # immediately before allowing it and reject a stale worker snapshot.
            runtime_state = self._runtime_state.collect()
            actual_domains = getattr(runtime_state, "direct_domains", None)
            rendered_domains = getattr(runtime_state, "rendered_domains", None)
            sequence_types = (tuple, list, set)
            if isinstance(actual_domains, sequence_types) and isinstance(
                rendered_domains,
                sequence_types,
            ):
                expected_domains = tuple(
                    sorted(
                        {
                            self._normalize_domain(domain)
                            for domain in direct_domains
                            if self._normalize_domain(domain)
                        },
                    ),
                )
                actual_domains = tuple(
                    sorted(
                        {
                            self._normalize_domain(domain)
                            for domain in actual_domains
                            if self._normalize_domain(domain)
                        },
                    ),
                )
                rendered_domains = tuple(
                    sorted(
                        {
                            self._normalize_domain(domain)
                            for domain in rendered_domains
                            if self._normalize_domain(domain)
                        },
                    ),
                )
                if (
                    actual_domains != expected_domains
                    or rendered_domains != expected_domains
                ):
                    raise RuntimeError(
                        "smart_routing_dns_full_reconcile_policy_changed: "
                        f"requested={expected_domains!r}; "
                        f"uci={actual_domains!r}; rendered={rendered_domains!r}",
                    )

        # Preserve the previously known ownership set. Never delete every
        # current ipset member merely because this worker's in-memory state is
        # incomplete (for example, immediately after backend startup).
        previous_ipv4_addresses = set(self._state_store.all_ipv4_addresses())
        previous_ipv6_addresses = set(self._state_store.all_ipv6_addresses())

        read_result = self._log_reader.read(cursor)
        if read_result.reset:
            # A reboot/log rotation starts a new observation epoch. Old DNS
            # ownership must not be carried into the new log. Return without
            # changing ipsets; the worker will rewind and replay the new log.
            self.reset_state()
            return SmartRoutingDnsCoordinatorResult(
                processed_responses=0,
                added_ipv4_addresses=(),
                removed_ipv4_addresses=(),
                cursor=read_result.cursor,
                log_reset=True,
                added_ipv6_addresses=(),
                removed_ipv6_addresses=(),
            )

        # Pending DNS transactions have an independent lifecycle. Prune them
        # on every reconciliation, including cycles with no new log lines.
        self._response_observer.prune_pending(direct_domains)

        self._state_store.prune_to_domains(direct_domains)
        active_after_prune_ipv4 = set(self._state_store.all_ipv4_addresses())
        active_after_prune_ipv6 = set(self._state_store.all_ipv6_addresses())
        pruned_ipv4_addresses = previous_ipv4_addresses - active_after_prune_ipv4
        pruned_ipv6_addresses = previous_ipv6_addresses - active_after_prune_ipv6

        if (
            not read_result.lines
            and not pruned_ipv4_addresses
            and not pruned_ipv6_addresses
            and not force_ipset_reconcile
            and not force_ipset_add_only
        ):
            return SmartRoutingDnsCoordinatorResult(
                processed_responses=0,
                added_ipv4_addresses=(),
                removed_ipv4_addresses=(),
                cursor=read_result.cursor,
                log_reset=read_result.reset,
                added_ipv6_addresses=(),
                removed_ipv6_addresses=(),
            )

        responses = (
            self._response_observer.parse_lines(
                read_result.lines,
                direct_domains,
            )
            if read_result.lines
            else ()
        )

        for response in responses:
            ipv4_addresses = response.ipv4_addresses or None
            ipv6_addresses = response.ipv6_addresses or None

            if ipv4_addresses is None and ipv6_addresses is None:
                continue

            self._state_store.update(
                response.domain,
                ipv4_addresses=ipv4_addresses,
                ipv6_addresses=ipv6_addresses,
            )

        active_ipv4_addresses = set(self._state_store.all_ipv4_addresses())
        active_ipv6_addresses = set(self._state_store.all_ipv6_addresses())
        removed_known_ipv4_addresses = previous_ipv4_addresses - active_ipv4_addresses
        removed_known_ipv6_addresses = previous_ipv6_addresses - active_ipv6_addresses

        # Unrelated DNS events, or a query whose response is split across log
        # chunks, must not trigger a global ipset diff against an incomplete
        # in-memory state. The observer retains pending transactions itself.
        if (
            not responses
            and not removed_known_ipv4_addresses
            and not removed_known_ipv6_addresses
            and not force_ipset_reconcile
            and not force_ipset_add_only
        ):
            return SmartRoutingDnsCoordinatorResult(
                processed_responses=0,
                added_ipv4_addresses=(),
                removed_ipv4_addresses=(),
                cursor=read_result.cursor,
                log_reset=read_result.reset,
                added_ipv6_addresses=(),
                removed_ipv6_addresses=(),
            )

        if runtime_state is None:
            runtime_state = self._runtime_state.collect()

        runtime_dns_ipv4_addresses = tuple(
            sorted(
                set(runtime_state.direct_ipv4_addresses)
                - set(runtime_state.static_direct_ipv4_addresses),
            ),
        )
        runtime_dns_ipv6_addresses = tuple(
            sorted(getattr(runtime_state, "direct_ipv6_addresses", ())),
        )

        reconciliation = self._ipset_reconciler.build(
            self._state_store,
            runtime_dns_ipv4_addresses,
            runtime_dns_ipv6_addresses,
        )

        static_ipv4_addresses = set(runtime_state.static_direct_ipv4_addresses)
        # Static DIRECT addresses are already routed by MAXVPN_DIRECT_STATIC.
        # Do not repeatedly add them to the DNS-derived set when a DIRECT
        # domain resolves to the same address.
        added = tuple(
            address
            for address in reconciliation.addresses_to_add
            if address not in static_ipv4_addresses
        )
        added_ipv6 = reconciliation.ipv6_addresses_to_add

        if force_ipset_reconcile:
            # Used only after initial bootstrap from a complete log. At that
            # point the per-domain state is a complete snapshot and a full diff
            # can safely remove unowned/stale entries.
            removed = reconciliation.addresses_to_remove
            removed_ipv6 = reconciliation.ipv6_addresses_to_remove
        elif force_ipset_add_only:
            # After an observed log rotation, the old log history is gone. We
            # can restore addresses confirmed by the new log, but cannot safely
            # delete unknown live entries whose ownership was in the old log.
            removed = ()
            removed_ipv6 = ()
        else:
            # During normal incremental operation, remove only addresses whose
            # prior DNS ownership was known and has now disappeared. This
            # preserves entries not yet observed by this worker instance and
            # IPs still shared by another active DIRECT domain.
            static_ipv4 = set(runtime_state.static_direct_ipv4_addresses)
            removed = tuple(
                sorted(removed_known_ipv4_addresses - static_ipv4),
            )
            removed_ipv6 = tuple(sorted(removed_known_ipv6_addresses))

        if dry_run:
            return SmartRoutingDnsCoordinatorResult(
                processed_responses=len(responses),
                added_ipv4_addresses=added,
                removed_ipv4_addresses=removed,
                cursor=read_result.cursor,
                log_reset=read_result.reset,
                added_ipv6_addresses=added_ipv6,
                removed_ipv6_addresses=removed_ipv6,
            )

        added_actual: tuple[str, ...] = ()
        removed_actual: tuple[str, ...] = ()
        added_ipv6_actual: tuple[str, ...] = ()
        removed_ipv6_actual: tuple[str, ...] = ()

        if added:
            added_actual = self._cleanup.add_addresses(added)

        if removed:
            removed_actual = self._cleanup.remove_stale(removed)

        if added_ipv6:
            add_ipv6 = getattr(
                self._cleanup,
                "add_ipv6_addresses",
                None,
            )
            if add_ipv6 is None:
                raise RuntimeError("smart_routing_dns_ipv6_cleanup_unsupported")
            added_ipv6_actual = add_ipv6(added_ipv6)

        if removed_ipv6:
            remove_ipv6 = getattr(
                self._cleanup,
                "remove_stale_ipv6",
                None,
            )
            if remove_ipv6 is None:
                raise RuntimeError("smart_routing_dns_ipv6_cleanup_unsupported")
            removed_ipv6_actual = remove_ipv6(removed_ipv6)

        return SmartRoutingDnsCoordinatorResult(
            processed_responses=len(responses),
            added_ipv4_addresses=added_actual,
            removed_ipv4_addresses=removed_actual,
            cursor=read_result.cursor,
            log_reset=read_result.reset,
            added_ipv6_addresses=added_ipv6_actual,
            removed_ipv6_addresses=removed_ipv6_actual,
        )

    def _reconcile_persistent(
        self,
        *,
        direct_domains: tuple[str, ...],
        cursor: SmartRoutingDnsLogCursor | None,
        dry_run: bool,
        force_ipset_reconcile: bool,
    ) -> SmartRoutingDnsCoordinatorResult:
        if force_ipset_reconcile:
            # The persisted ownership map is authoritative only for addresses
            # it has observed. A global live-set diff could delete unrelated
            # or legacy members and is therefore forbidden in durable mode.
            raise RuntimeError(
                "smart_routing_dns_full_reconcile_disabled_with_persistent_ownership"
            )
        if not self._persistent_state_initialized:
            raise RuntimeError("smart_routing_dns_persistence_not_initialized")

        previous_states = self._state_store.all_states()
        previous_ipv4 = set(self._state_store.all_ipv4_addresses())
        previous_ipv6 = set(self._state_store.all_ipv6_addresses())

        # Mutate a candidate snapshot. The live in-memory store is swapped only
        # after PostgreSQL commits the ownership and outbox changes together.
        candidate = SmartRoutingDnsDomainStateStore()
        candidate.replace_all(previous_states)

        read_result = self._log_reader.read(cursor)
        if read_result.reset:
            self._response_observer.reset()
            return SmartRoutingDnsCoordinatorResult(
                processed_responses=0,
                added_ipv4_addresses=(),
                removed_ipv4_addresses=(),
                cursor=read_result.cursor,
                log_reset=True,
            )

        self._response_observer.prune_pending(direct_domains)
        candidate.prune_to_domains(direct_domains)

        responses = (
            self._response_observer.parse_lines(read_result.lines, direct_domains)
            if read_result.lines
            else ()
        )
        for response in responses:
            ipv4_addresses = response.ipv4_addresses or None
            ipv6_addresses = response.ipv6_addresses or None
            if ipv4_addresses is None and ipv6_addresses is None:
                continue
            candidate.update(
                response.domain,
                ipv4_addresses=ipv4_addresses,
                ipv6_addresses=ipv6_addresses,
            )

        current_states = candidate.all_states()
        current_ipv4 = set(candidate.all_ipv4_addresses())
        current_ipv6 = set(candidate.all_ipv6_addresses())
        added_ipv4 = tuple(sorted(current_ipv4 - previous_ipv4))
        removed_ipv4 = tuple(sorted(previous_ipv4 - current_ipv4))
        added_ipv6 = tuple(sorted(current_ipv6 - previous_ipv6))
        removed_ipv6 = tuple(sorted(previous_ipv6 - current_ipv6))

        if current_states != previous_states:
            self._state_repository.persist_snapshot_and_enqueue(
                domain_states=current_states,
                added_ipv4_addresses=added_ipv4,
                removed_ipv4_addresses=removed_ipv4,
                added_ipv6_addresses=added_ipv6,
                removed_ipv6_addresses=removed_ipv6,
            )
            self._state_store.replace_all(current_states)

        if dry_run:
            return SmartRoutingDnsCoordinatorResult(
                processed_responses=len(responses),
                added_ipv4_addresses=added_ipv4,
                removed_ipv4_addresses=removed_ipv4,
                cursor=read_result.cursor,
                log_reset=False,
                added_ipv6_addresses=added_ipv6,
                removed_ipv6_addresses=removed_ipv6,
            )

        applied_add4, applied_remove4, applied_add6, applied_remove6 = (
            self.flush_pending_ipset_operations(allow_deletions=True)
        )
        return SmartRoutingDnsCoordinatorResult(
            processed_responses=len(responses),
            added_ipv4_addresses=applied_add4,
            removed_ipv4_addresses=applied_remove4,
            cursor=read_result.cursor,
            log_reset=False,
            added_ipv6_addresses=applied_add6,
            removed_ipv6_addresses=applied_remove6,
        )

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        return domain.strip().lower().rstrip(".")
