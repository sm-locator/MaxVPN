from dataclasses import dataclass
from unittest.mock import Mock

import pytest
from backend.services.smart_routing_dns_domain_state import (
    SmartRoutingDnsDomainState,
    SmartRoutingDnsDomainStateStore,
)
from backend.services.smart_routing_dns_log_reader import (
    SmartRoutingDnsLogCursor,
    SmartRoutingDnsLogReadResult,
)
from backend.services.smart_routing_dns_reconciliation_coordinator import (
    SmartRoutingDnsReconciliationCoordinator,
)
from backend.services.smart_routing_dns_response_observer import (
    SmartRoutingDnsResponse,
    SmartRoutingDnsResponseObserver,
)


@dataclass(frozen=True)
class Operation:
    address_family: str
    address: str
    desired_present: bool


class FakeStateRepository:
    def __init__(self, states=()):
        self.states = tuple(states)
        self.pending: dict[tuple[str, str], Operation] = {}
        self.persist_calls = []
        self.fail_persist = False

    def load_domain_states(self):
        return self.states

    def enqueue_present_addresses(self, ipv4_addresses=(), ipv6_addresses=()):
        for address in ipv4_addresses:
            self._upsert("ipv4", address, True)
        for address in ipv6_addresses:
            self._upsert("ipv6", address, True)

    def persist_snapshot_and_enqueue(
        self,
        *,
        domain_states,
        added_ipv4_addresses=(),
        removed_ipv4_addresses=(),
        added_ipv6_addresses=(),
        removed_ipv6_addresses=(),
    ):
        self.persist_calls.append(
            (
                tuple(domain_states),
                tuple(added_ipv4_addresses),
                tuple(removed_ipv4_addresses),
                tuple(added_ipv6_addresses),
                tuple(removed_ipv6_addresses),
            )
        )
        if self.fail_persist:
            raise RuntimeError("database unavailable")
        self.states = tuple(domain_states)
        for address in added_ipv4_addresses:
            self._upsert("ipv4", address, True)
        for address in added_ipv6_addresses:
            self._upsert("ipv6", address, True)
        for address in removed_ipv4_addresses:
            self._upsert("ipv4", address, False)
        for address in removed_ipv6_addresses:
            self._upsert("ipv6", address, False)

    def _upsert(self, family, address, desired_present):
        self.pending[(family, address)] = Operation(
            family,
            address,
            desired_present,
        )

    def list_pending_operations(self):
        return tuple(
            sorted(
                self.pending.values(),
                key=lambda operation: (
                    not operation.desired_present,
                    operation.address,
                ),
            )
        )

    def acknowledge_operation(self, operation):
        key = (operation.address_family, operation.address)
        current = self.pending.get(key)
        if current == operation:
            del self.pending[key]
            return True
        return False


class FakeRuntimeState:
    def __init__(self, direct=(), static=(), direct6=(), static6=()):
        self.direct = set(direct)
        self.static = set(static)
        self.direct6 = set(direct6)
        self.static6 = set(static6)

    def collect(self):
        return Mock(
            direct_ipv4_addresses=tuple(sorted(self.direct | self.static)),
            static_direct_ipv4_addresses=tuple(sorted(self.static)),
            direct_ipv6_addresses=tuple(sorted(self.direct6 | self.static6)),
            static_direct_ipv6_addresses=tuple(sorted(self.static6)),
        )


class FakeCleanup:
    def __init__(self):
        self.added4 = []
        self.removed4 = []
        self.added6 = []
        self.removed6 = []
        self.fail_add4 = False
        self.fail_remove4 = False

    def add_addresses(self, addresses):
        if self.fail_add4:
            self.fail_add4 = False
            raise RuntimeError("temporary add failure")
        self.added4.extend(addresses)
        return tuple(addresses)

    def remove_stale(self, addresses):
        if self.fail_remove4:
            self.fail_remove4 = False
            raise RuntimeError("temporary delete failure")
        self.removed4.extend(addresses)
        return tuple(addresses)

    def add_ipv6_addresses(self, addresses):
        self.added6.extend(addresses)
        return tuple(addresses)

    def remove_stale_ipv6(self, addresses):
        self.removed6.extend(addresses)
        return tuple(addresses)


def make_coordinator(*, states=(), direct=(), static=(), direct6=(), static6=()):
    reader = Mock()
    observer = SmartRoutingDnsResponseObserver()
    state_store = SmartRoutingDnsDomainStateStore()
    runtime = FakeRuntimeState(direct, static, direct6, static6)
    cleanup = FakeCleanup()
    repository = FakeStateRepository(states)
    coordinator = SmartRoutingDnsReconciliationCoordinator(
        log_reader=reader,
        response_observer=observer,
        state_store=state_store,
        ipset_reconciler=Mock(),
        runtime_state=runtime,
        cleanup=cleanup,
        state_repository=repository,
    )
    return coordinator, reader, observer, state_store, runtime, cleanup, repository


def test_initialize_restores_domain_map_and_enqueues_only_known_additions():
    state = SmartRoutingDnsDomainState(
        "example.com",
        ("192.0.2.10",),
        ("2001:db8::10",),
    )
    coordinator, _, _, store, _, _, repository = make_coordinator(states=(state,))

    coordinator.initialize_persistent_state()

    assert store.all_states() == (state,)
    assert repository.pending == {}


def test_log_reset_preserves_persistent_domain_ownership():
    state = SmartRoutingDnsDomainState("example.com", ("192.0.2.10",))
    coordinator, reader, observer, store, _, _, _ = make_coordinator(states=(state,))
    coordinator.initialize_persistent_state()
    observer.reset = Mock()
    cursor = SmartRoutingDnsLogCursor(200, 0)
    reader.read.return_value = SmartRoutingDnsLogReadResult((), cursor, True)

    result = coordinator.reconcile(direct_domains=("example.com",), cursor=cursor)

    assert result.log_reset is True
    assert store.get("example.com") == state
    observer.reset.assert_called_once_with()


def test_database_failure_does_not_publish_candidate_state_to_memory():
    old_state = SmartRoutingDnsDomainState("example.com", ("192.0.2.10",))
    coordinator, reader, observer, store, _, _, repository = make_coordinator(
        states=(old_state,),
        direct=("192.0.2.10",),
    )
    coordinator.initialize_persistent_state()
    repository.pending.clear()
    repository.fail_persist = True
    cursor = SmartRoutingDnsLogCursor(10, 100)
    reader.read.return_value = SmartRoutingDnsLogReadResult(
        ("dns-event",),
        cursor,
        False,
    )
    observer.parse_lines = Mock(
        return_value=(
            SmartRoutingDnsResponse(
                process_id=1,
                transaction_id="2",
                domain="example.com",
                ipv4_addresses=("192.0.2.20",),
            ),
        )
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        coordinator.reconcile(direct_domains=("example.com",), cursor=cursor)

    assert store.get("example.com") == old_state
    assert repository.pending == {}
    assert repository.persist_calls[0][1:3] == (
        ("192.0.2.20",),
        ("192.0.2.10",),
    )


def test_dns_rollover_persists_add_and_delete_intents_then_applies_add_first():
    old_state = SmartRoutingDnsDomainState("example.com", ("192.0.2.10",))
    (
        coordinator,
        reader,
        observer,
        store,
        runtime,
        cleanup,
        repository,
    ) = make_coordinator(
        states=(old_state,),
        direct=("192.0.2.10",),
    )
    coordinator.initialize_persistent_state()
    coordinator.flush_pending_ipset_operations()
    repository.pending.clear()

    cursor = SmartRoutingDnsLogCursor(10, 200)
    reader.read.return_value = SmartRoutingDnsLogReadResult(
        ("dns-event",),
        cursor,
        False,
    )
    observer.parse_lines = Mock(
        return_value=(
            SmartRoutingDnsResponse(
                process_id=1,
                transaction_id="3",
                domain="example.com",
                ipv4_addresses=("192.0.2.20",),
            ),
        )
    )
    runtime.direct = {"192.0.2.10"}

    result = coordinator.reconcile(direct_domains=("example.com",), cursor=cursor)

    assert store.get("example.com").ipv4_addresses == ("192.0.2.20",)
    assert cleanup.added4 == ["192.0.2.20"]
    assert cleanup.removed4 == ["192.0.2.10"]
    assert result.added_ipv4_addresses == ("192.0.2.20",)
    assert result.removed_ipv4_addresses == ("192.0.2.10",)
    assert repository.pending == {}


def test_failed_add_remains_in_outbox_and_is_retried():
    state = SmartRoutingDnsDomainState("example.com", ("192.0.2.10",))
    coordinator, _, _, _, _, cleanup, repository = make_coordinator(states=(state,))
    coordinator.initialize_persistent_state()
    cleanup.fail_add4 = True

    with pytest.raises(RuntimeError, match="temporary add failure"):
        coordinator.flush_pending_ipset_operations()

    assert ("ipv4", "192.0.2.10") in repository.pending

    coordinator.flush_pending_ipset_operations()

    assert cleanup.added4 == ["192.0.2.10"]
    assert repository.pending == {}


def test_failed_delete_remains_in_outbox_and_is_retried():
    coordinator, _, _, _, _, cleanup, repository = make_coordinator()
    repository._upsert("ipv4", "192.0.2.10", False)
    coordinator.initialize_persistent_state()
    cleanup.fail_remove4 = True

    with pytest.raises(RuntimeError, match="temporary delete failure"):
        coordinator.flush_pending_ipset_operations()

    assert repository.pending[("ipv4", "192.0.2.10")].desired_present is False

    coordinator.flush_pending_ipset_operations()

    assert cleanup.removed4 == ["192.0.2.10"]
    assert repository.pending == {}


def test_unknown_live_ip_is_not_deleted_by_persistent_reconciliation():
    coordinator, _, _, _, runtime, cleanup, repository = make_coordinator(
        direct=("198.51.100.99",),
    )
    coordinator.initialize_persistent_state()

    coordinator.flush_pending_ipset_operations()

    assert runtime.direct == {"198.51.100.99"}
    assert cleanup.removed4 == []
    assert repository.pending == {}


def test_shared_ip_remains_owned_until_last_domain_releases_it():
    states = (
        SmartRoutingDnsDomainState("one.example", ("192.0.2.10",)),
        SmartRoutingDnsDomainState("two.example", ("192.0.2.10",)),
    )
    coordinator, reader, observer, _, _, _, repository = make_coordinator(states=states)
    coordinator.initialize_persistent_state()
    repository.pending.clear()
    cursor = SmartRoutingDnsLogCursor(10, 200)
    reader.read.return_value = SmartRoutingDnsLogReadResult(
        ("dns-event",),
        cursor,
        False,
    )
    observer.parse_lines = Mock(
        return_value=(
            SmartRoutingDnsResponse(
                process_id=1,
                transaction_id="4",
                domain="one.example",
                ipv4_addresses=("192.0.2.20",),
            ),
        )
    )

    coordinator.reconcile(
        direct_domains=("one.example", "two.example"),
        cursor=cursor,
        dry_run=True,
    )

    assert ("ipv4", "192.0.2.10") not in repository.pending
    assert repository.pending[("ipv4", "192.0.2.20")].desired_present is True


def test_static_ipv4_defers_delete_until_static_rule_is_removed():
    coordinator, _, _, _, runtime, cleanup, repository = make_coordinator(
        static=("192.0.2.10",),
    )
    coordinator.initialize_persistent_state()
    repository._upsert("ipv4", "192.0.2.10", False)

    coordinator.flush_pending_ipset_operations()
    assert ("ipv4", "192.0.2.10") in repository.pending
    assert cleanup.removed4 == []

    runtime.static.clear()
    coordinator.flush_pending_ipset_operations()
    assert repository.pending == {}
    assert cleanup.removed4 == ["192.0.2.10"]


def test_empty_direct_policy_deletes_only_previously_owned_addresses():
    state = SmartRoutingDnsDomainState("example.com", ("192.0.2.10",))
    coordinator, reader, _, store, runtime, cleanup, repository = make_coordinator(
        states=(state,),
        direct=("192.0.2.10", "198.51.100.99"),
    )
    coordinator.initialize_persistent_state()
    cursor = SmartRoutingDnsLogCursor(10, 100)
    reader.read.return_value = SmartRoutingDnsLogReadResult((), cursor, False)

    result = coordinator.reconcile(direct_domains=(), cursor=cursor)

    assert result.removed_ipv4_addresses == ("192.0.2.10",)
    assert store.all_states() == ()
    assert cleanup.removed4 == ["192.0.2.10"]
    assert "198.51.100.99" in runtime.direct
    assert repository.pending == {}


def test_persistent_reconciliation_rejects_unsafe_global_full_diff():
    coordinator, reader, _, _, _, cleanup, _ = make_coordinator()
    coordinator.initialize_persistent_state()

    with pytest.raises(
        RuntimeError,
        match="full_reconcile_disabled_with_persistent_ownership",
    ):
        coordinator.reconcile(
            direct_domains=("example.com",),
            cursor=SmartRoutingDnsLogCursor(10, 100),
            force_ipset_reconcile=True,
        )

    reader.read.assert_not_called()
    assert cleanup.removed4 == []


def test_new_owner_reverses_pending_delete_to_present() -> None:
    old_state = SmartRoutingDnsDomainState("old.example", ("192.0.2.10",))
    coordinator, reader, observer, store, _, cleanup, repository = make_coordinator(
        states=(old_state,),
        direct=("192.0.2.10",),
    )
    coordinator.initialize_persistent_state()
    repository.pending.clear()
    cleanup.fail_remove4 = True

    empty_cursor = SmartRoutingDnsLogCursor(10, 100)
    reader.read.return_value = SmartRoutingDnsLogReadResult((), empty_cursor, False)
    with pytest.raises(RuntimeError, match="temporary delete failure"):
        coordinator.reconcile(direct_domains=(), cursor=empty_cursor)

    assert repository.pending[("ipv4", "192.0.2.10")].desired_present is False
    assert store.all_states() == ()

    response_cursor = SmartRoutingDnsLogCursor(10, 200)
    reader.read.return_value = SmartRoutingDnsLogReadResult(
        ("dns-event",),
        response_cursor,
        False,
    )
    observer.parse_lines = Mock(
        return_value=(
            SmartRoutingDnsResponse(
                process_id=1,
                transaction_id="8",
                domain="new.example",
                ipv4_addresses=("192.0.2.10",),
            ),
        )
    )

    coordinator.reconcile(direct_domains=("new.example",), cursor=empty_cursor)

    assert store.get("new.example").ipv4_addresses == ("192.0.2.10",)
    assert repository.pending == {}
    # The address remained live throughout the failed deletion, so the newer
    # present intent can be acknowledged without an unnecessary ADD command.
    assert cleanup.added4 == []
    assert cleanup.removed4 == []


def test_restore_missing_runtime_ipsets_from_persistent_ownership():
    state = SmartRoutingDnsDomainState(
        "example.com",
        ("192.0.2.10", "192.0.2.20"),
        ("2001:db8::10", "2001:db8::20"),
    )

    # Simulate router reboot:
    # owned dynamic addresses are missing, while unrelated and static
    # entries are still present in their respective ipsets.
    coordinator, _, _, store, runtime, cleanup, repository = make_coordinator(
        states=(state,),
        direct=("198.51.100.99",),
        static=("192.0.2.20",),
        direct6=("2001:db8::99",),
        static6=("2001:db8::20",),
    )

    coordinator.initialize_persistent_state()

    assert store.all_states() == (state,)
    assert repository.pending == {}

    result = coordinator.flush_pending_ipset_operations()

    # Restore only missing addresses owned by persistent DNS state.
    assert result == (
        ("192.0.2.10",),
        (),
        ("2001:db8::10",),
        (),
    )
    assert cleanup.added4 == ["192.0.2.10"]
    assert cleanup.added6 == ["2001:db8::10"]

    # Never delete unknown or static entries during recovery.
    assert cleanup.removed4 == []
    assert cleanup.removed6 == []
    assert runtime.direct == {"198.51.100.99"}
    assert runtime.static == {"192.0.2.20"}
    assert runtime.direct6 == {"2001:db8::99"}
    assert runtime.static6 == {"2001:db8::20"}

    # Every successfully applied operation must be acknowledged.
    assert repository.pending == {}
    assert store.all_states() == (state,)
