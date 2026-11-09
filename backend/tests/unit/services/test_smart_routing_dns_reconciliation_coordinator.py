from unittest.mock import Mock

import pytest
from backend.models.command_result import CommandResult
from backend.services.smart_routing_dns_domain_state import (
    SmartRoutingDnsDomainStateStore,
)
from backend.services.smart_routing_dns_ipset_reconciler import (
    SmartRoutingDnsIpSetReconciler,
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


def make_result(stdout: str = "") -> CommandResult:
    return CommandResult(
        returncode=0,
        stdout=stdout,
        stderr="",
    )


def make_coordinator():
    reader = Mock()
    observer = Mock(spec=SmartRoutingDnsResponseObserver)
    store = SmartRoutingDnsDomainStateStore()
    reconciler = SmartRoutingDnsIpSetReconciler()
    runtime_state = Mock()
    cleanup = Mock()

    cleanup.add_addresses.side_effect = lambda addresses: addresses
    cleanup.remove_stale.side_effect = lambda addresses: addresses

    coordinator = SmartRoutingDnsReconciliationCoordinator(
        log_reader=reader,
        response_observer=observer,
        state_store=store,
        ipset_reconciler=reconciler,
        runtime_state=runtime_state,
        cleanup=cleanup,
    )

    return coordinator, reader, observer, runtime_state, cleanup


def test_no_new_log_lines_is_noop() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()

    cursor = SmartRoutingDnsLogCursor(10, 100)

    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=(),
        cursor=cursor,
        reset=False,
    )

    result = coordinator.reconcile(
        direct_domains=("example.com",),
        cursor=cursor,
    )

    assert result.processed_responses == 0
    assert result.added_ipv4_addresses == ()
    assert result.removed_ipv4_addresses == ()
    assert result.cursor == cursor
    assert result.log_reset is False

    observer.parse_lines.assert_not_called()
    observer.prune_pending.assert_called_once_with(("example.com",))
    runtime_state.collect.assert_not_called()
    cleanup.add_addresses.assert_not_called()
    cleanup.remove_stale.assert_not_called()


def test_successful_dns_response_adds_new_ip() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()

    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=("dns-event",),
        cursor=SmartRoutingDnsLogCursor(10, 200),
        reset=False,
    )

    observer.parse_lines.return_value = (
        SmartRoutingDnsResponse(
            process_id=100,
            transaction_id="11",
            domain="example.com",
            ipv4_addresses=("1.1.1.1",),
        ),
    )

    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=(),
        static_direct_ipv4_addresses=(),
        direct_ipv6_addresses=(),
    )

    result = coordinator.reconcile(
        direct_domains=("example.com",),
        cursor=SmartRoutingDnsLogCursor(10, 100),
    )

    assert result.processed_responses == 1
    assert result.added_ipv4_addresses == ("1.1.1.1",)
    assert result.removed_ipv4_addresses == ()

    cleanup.add_addresses.assert_called_once_with(("1.1.1.1",))
    cleanup.remove_stale.assert_not_called()


def test_dns_rollover_adds_new_and_removes_old() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()
    coordinator._state_store.update("example.com", ("1.1.1.1",))

    first_cursor = SmartRoutingDnsLogCursor(10, 100)

    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=("dns-event",),
        cursor=SmartRoutingDnsLogCursor(10, 200),
        reset=False,
    )

    observer.parse_lines.return_value = (
        SmartRoutingDnsResponse(
            process_id=100,
            transaction_id="11",
            domain="example.com",
            ipv4_addresses=("2.2.2.2",),
        ),
    )

    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=("1.1.1.1",),
        static_direct_ipv4_addresses=(),
        direct_ipv6_addresses=(),
    )

    cleanup.add_addresses.return_value = ("2.2.2.2",)
    cleanup.remove_stale.return_value = ("1.1.1.1",)

    result = coordinator.reconcile(
        direct_domains=("example.com",),
        cursor=first_cursor,
    )

    assert result.added_ipv4_addresses == ("2.2.2.2",)
    assert result.removed_ipv4_addresses == ("1.1.1.1",)

    cleanup.add_addresses.assert_called_once_with(("2.2.2.2",))
    cleanup.remove_stale.assert_called_once_with(("1.1.1.1",))


def test_shared_ip_is_not_removed() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()

    coordinator._state_store.update(
        "two.example",
        ("1.1.1.1",),
    )

    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=("dns-event",),
        cursor=SmartRoutingDnsLogCursor(10, 200),
        reset=False,
    )

    observer.parse_lines.return_value = (
        SmartRoutingDnsResponse(
            process_id=100,
            transaction_id="11",
            domain="one.example",
            ipv4_addresses=("2.2.2.2",),
        ),
    )

    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=("1.1.1.1",),
        static_direct_ipv4_addresses=(),
        direct_ipv6_addresses=(),
    )

    cleanup.add_addresses.return_value = ("2.2.2.2",)
    cleanup.remove_stale.return_value = ()

    result = coordinator.reconcile(
        direct_domains=("one.example", "two.example"),
        cursor=SmartRoutingDnsLogCursor(10, 100),
    )

    assert result.added_ipv4_addresses == ("2.2.2.2",)
    assert result.removed_ipv4_addresses == ()

    cleanup.add_addresses.assert_called_once_with(("2.2.2.2",))
    cleanup.remove_stale.assert_not_called()


def test_dry_run_does_not_modify_ipset() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()

    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=("dns-event",),
        cursor=SmartRoutingDnsLogCursor(10, 200),
        reset=False,
    )

    observer.parse_lines.return_value = (
        SmartRoutingDnsResponse(
            process_id=100,
            transaction_id="11",
            domain="example.com",
            ipv4_addresses=("1.1.1.1",),
        ),
    )

    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=(),
        static_direct_ipv4_addresses=(),
        direct_ipv6_addresses=(),
    )

    result = coordinator.reconcile(
        direct_domains=("example.com",),
        cursor=SmartRoutingDnsLogCursor(10, 100),
        dry_run=True,
    )

    assert result.added_ipv4_addresses == ("1.1.1.1",)
    assert result.removed_ipv4_addresses == ()

    cleanup.add_addresses.assert_not_called()
    cleanup.remove_stale.assert_not_called()


def test_full_reconcile_after_bootstrap_removes_unowned_live_members() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()
    coordinator._state_store.update("example.com", ("198.51.100.20",))

    cursor = SmartRoutingDnsLogCursor(10, 300)
    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=(),
        cursor=cursor,
        reset=False,
    )
    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=("198.51.100.10", "198.51.100.20"),
        static_direct_ipv4_addresses=(),
        direct_ipv6_addresses=(),
    )
    cleanup.remove_stale.return_value = ("198.51.100.10",)

    result = coordinator.reconcile(
        direct_domains=("example.com",),
        cursor=cursor,
        force_ipset_reconcile=True,
    )

    assert result.added_ipv4_addresses == ()
    assert result.removed_ipv4_addresses == ("198.51.100.10",)
    cleanup.remove_stale.assert_called_once_with(("198.51.100.10",))


def test_force_add_only_bootstrap_never_removes_unowned_live_members() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()
    coordinator._state_store.update("example.com", ("198.51.100.20",))

    cursor = SmartRoutingDnsLogCursor(10, 300)
    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=(),
        cursor=cursor,
        reset=False,
    )
    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=("198.51.100.10",),
        static_direct_ipv4_addresses=(),
        direct_ipv6_addresses=(),
    )
    cleanup.add_addresses.return_value = ("198.51.100.20",)

    result = coordinator.reconcile(
        direct_domains=("example.com",),
        cursor=cursor,
        force_ipset_add_only=True,
    )

    assert result.added_ipv4_addresses == ("198.51.100.20",)
    assert result.removed_ipv4_addresses == ()
    cleanup.add_addresses.assert_called_once_with(("198.51.100.20",))
    cleanup.remove_stale.assert_not_called()


def test_unrelated_dns_event_does_not_delete_untracked_direct_entries() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()

    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=("unrelated DNS query/reply",),
        cursor=SmartRoutingDnsLogCursor(10, 300),
        reset=False,
    )
    observer.parse_lines.return_value = ()
    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=("198.51.100.10", "198.51.100.20"),
        static_direct_ipv4_addresses=(),
        direct_ipv6_addresses=(),
    )

    result = coordinator.reconcile(
        direct_domains=("example.com",),
        cursor=SmartRoutingDnsLogCursor(10, 200),
    )

    assert result.processed_responses == 0
    assert result.removed_ipv4_addresses == ()
    runtime_state.collect.assert_not_called()
    cleanup.remove_stale.assert_not_called()


def test_first_direct_response_does_not_delete_unowned_existing_entries() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()

    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=("DNS response for example.com",),
        cursor=SmartRoutingDnsLogCursor(10, 300),
        reset=False,
    )
    observer.parse_lines.return_value = (
        SmartRoutingDnsResponse(
            process_id=100,
            transaction_id="11",
            domain="example.com",
            ipv4_addresses=("198.51.100.20",),
        ),
    )
    # This represents the live set when the backend starts with an empty
    # in-memory domain map: one old/unowned IP and the new DNS answer.
    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=("198.51.100.10", "198.51.100.20"),
        static_direct_ipv4_addresses=(),
        direct_ipv6_addresses=(),
    )

    result = coordinator.reconcile(
        direct_domains=("example.com",),
        cursor=SmartRoutingDnsLogCursor(10, 200),
    )

    assert result.added_ipv4_addresses == ()
    assert result.removed_ipv4_addresses == ()
    cleanup.remove_stale.assert_not_called()


def test_log_reset_is_propagated() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()

    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=(),
        cursor=SmartRoutingDnsLogCursor(99, 20),
        reset=True,
    )

    result = coordinator.reconcile(
        direct_domains=("example.com",),
        cursor=SmartRoutingDnsLogCursor(10, 100),
    )

    assert result.log_reset is True
    assert result.cursor == SmartRoutingDnsLogCursor(99, 20)


def test_domains_are_normalized_before_parser() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()

    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=("dns-event",),
        cursor=SmartRoutingDnsLogCursor(10, 200),
        reset=False,
    )

    observer.parse_lines.return_value = ()
    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=(),
        static_direct_ipv4_addresses=(),
        direct_ipv6_addresses=(),
    )

    coordinator.reconcile(
        direct_domains=(" Example.COM. ",),
    )

    observer.parse_lines.assert_called_once_with(
        ("dns-event",),
        (" Example.COM. ",),
    )


def test_cursor_advances_even_when_unrelated_events_are_ignored() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()

    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=("unrelated",),
        cursor=SmartRoutingDnsLogCursor(10, 300),
        reset=False,
    )

    observer.parse_lines.return_value = ()
    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=(),
        static_direct_ipv4_addresses=(),
        direct_ipv6_addresses=(),
    )

    result = coordinator.reconcile(
        direct_domains=("example.com",),
    )

    assert result.cursor == SmartRoutingDnsLogCursor(10, 300)
    assert result.processed_responses == 0
    assert cleanup.add_addresses.call_count == 0
    assert cleanup.remove_stale.call_count == 0


def test_reconciliation_never_removes_static_direct_addresses():
    from unittest.mock import Mock

    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()

    reader.read.return_value = Mock(
        lines=(
            "dnsmasq[100]: 1 127.0.0.1/10000 "
            "query[A] maxvpn-test.gps.navy from 127.0.0.1",
            "dnsmasq[100]: 1 127.0.0.1/10000 "
            "reply maxvpn-test.gps.navy is 81.90.181.115",
        ),
        cursor=SmartRoutingDnsLogCursor(100, 200),
        reset=False,
    )

    observer.parse_lines.return_value = (
        SmartRoutingDnsResponse(
            process_id=100,
            transaction_id="1",
            domain="maxvpn-test.gps.navy",
            ipv4_addresses=("81.90.181.115",),
        ),
    )

    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=(
            "81.90.181.115",
            "81.90.182.109",
            "31.25.243.222",
        ),
        static_direct_ipv4_addresses=(
            "81.90.182.109",
            "31.25.243.222",
        ),
        direct_ipv6_addresses=(),
    )

    result = coordinator.reconcile(
        direct_domains=("gps.navy",),
    )

    assert "81.90.182.109" not in result.removed_ipv4_addresses
    assert "31.25.243.222" not in result.removed_ipv4_addresses


def test_dns_response_does_not_readd_static_direct_ip() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()

    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=("dns-event",),
        cursor=SmartRoutingDnsLogCursor(10, 200),
        reset=False,
    )

    observer.parse_lines.return_value = (
        SmartRoutingDnsResponse(
            process_id=100,
            transaction_id="11",
            domain="example.com",
            ipv4_addresses=("81.90.182.109",),
        ),
    )

    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=("81.90.182.109",),
        static_direct_ipv4_addresses=("81.90.182.109",),
        direct_ipv6_addresses=(),
    )

    result = coordinator.reconcile(
        direct_domains=("example.com",),
        cursor=SmartRoutingDnsLogCursor(10, 100),
    )

    assert result.processed_responses == 1
    assert result.added_ipv4_addresses == ()
    assert result.removed_ipv4_addresses == ()
    cleanup.add_addresses.assert_not_called()
    cleanup.remove_stale.assert_not_called()


def test_successful_aaaa_response_adds_new_ipv6() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()

    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=("dns-event",),
        cursor=SmartRoutingDnsLogCursor(10, 200),
        reset=False,
    )

    observer.parse_lines.return_value = (
        SmartRoutingDnsResponse(
            process_id=100,
            transaction_id="11",
            domain="example.com",
            ipv4_addresses=(),
            ipv6_addresses=("2001:db8::10",),
        ),
    )

    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=(),
        static_direct_ipv4_addresses=(),
        direct_ipv6_addresses=(),
    )

    cleanup.add_ipv6_addresses.return_value = ("2001:db8::10",)

    result = coordinator.reconcile(
        direct_domains=("example.com",),
        cursor=SmartRoutingDnsLogCursor(10, 100),
    )

    assert result.processed_responses == 1
    assert result.added_ipv4_addresses == ()
    assert result.removed_ipv4_addresses == ()
    assert result.added_ipv6_addresses == ("2001:db8::10",)
    assert result.removed_ipv6_addresses == ()

    cleanup.add_addresses.assert_not_called()
    cleanup.remove_stale.assert_not_called()
    cleanup.add_ipv6_addresses.assert_called_once_with(
        ("2001:db8::10",),
    )
    cleanup.remove_stale_ipv6.assert_not_called()


def test_aaaa_rollover_adds_new_and_removes_old_ipv6() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()

    coordinator._state_store.update(
        "example.com",
        ipv6_addresses=("2001:db8::10",),
    )

    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=("dns-event",),
        cursor=SmartRoutingDnsLogCursor(10, 200),
        reset=False,
    )

    observer.parse_lines.return_value = (
        SmartRoutingDnsResponse(
            process_id=100,
            transaction_id="12",
            domain="example.com",
            ipv4_addresses=(),
            ipv6_addresses=("2001:db8::11",),
        ),
    )

    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=(),
        static_direct_ipv4_addresses=(),
        direct_ipv6_addresses=("2001:db8::10",),
    )

    cleanup.add_ipv6_addresses.return_value = ("2001:db8::11",)
    cleanup.remove_stale_ipv6.return_value = ("2001:db8::10",)

    result = coordinator.reconcile(
        direct_domains=("example.com",),
        cursor=SmartRoutingDnsLogCursor(10, 100),
    )

    assert result.added_ipv6_addresses == ("2001:db8::11",)
    assert result.removed_ipv6_addresses == ("2001:db8::10",)

    cleanup.add_ipv6_addresses.assert_called_once_with(
        ("2001:db8::11",),
    )
    cleanup.remove_stale_ipv6.assert_called_once_with(
        ("2001:db8::10",),
    )


def test_ipv4_and_ipv6_are_reconciled_independently() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()

    coordinator._state_store.update(
        "example.com",
        ipv4_addresses=("192.0.2.10",),
        ipv6_addresses=("2001:db8::10",),
    )

    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=("dns-event",),
        cursor=SmartRoutingDnsLogCursor(10, 200),
        reset=False,
    )

    observer.parse_lines.return_value = (
        SmartRoutingDnsResponse(
            process_id=100,
            transaction_id="13",
            domain="example.com",
            ipv4_addresses=("192.0.2.10",),
            ipv6_addresses=("2001:db8::11",),
        ),
    )

    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=("192.0.2.10",),
        static_direct_ipv4_addresses=(),
        direct_ipv6_addresses=("2001:db8::10",),
    )

    cleanup.add_ipv6_addresses.return_value = ("2001:db8::11",)
    cleanup.remove_stale_ipv6.return_value = ("2001:db8::10",)

    result = coordinator.reconcile(
        direct_domains=("example.com",),
        cursor=SmartRoutingDnsLogCursor(10, 100),
    )

    assert result.added_ipv4_addresses == ()
    assert result.removed_ipv4_addresses == ()
    assert result.added_ipv6_addresses == ("2001:db8::11",)
    assert result.removed_ipv6_addresses == ("2001:db8::10",)

    cleanup.add_addresses.assert_not_called()
    cleanup.remove_stale.assert_not_called()
    cleanup.add_ipv6_addresses.assert_called_once_with(
        ("2001:db8::11",),
    )
    cleanup.remove_stale_ipv6.assert_called_once_with(
        ("2001:db8::10",),
    )


def test_removed_direct_domain_cleans_stale_ipv6() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()

    coordinator._state_store.update(
        "removed.example",
        ipv6_addresses=("2001:db8::20",),
    )

    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=(),
        cursor=SmartRoutingDnsLogCursor(10, 200),
        reset=False,
    )

    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=(),
        static_direct_ipv4_addresses=(),
        direct_ipv6_addresses=("2001:db8::20",),
    )

    cleanup.remove_stale_ipv6.return_value = ("2001:db8::20",)

    result = coordinator.reconcile(
        direct_domains=("keep.example",),
        cursor=SmartRoutingDnsLogCursor(10, 100),
    )

    assert result.processed_responses == 0
    assert result.added_ipv6_addresses == ()
    assert result.removed_ipv6_addresses == ("2001:db8::20",)

    observer.parse_lines.assert_not_called()
    cleanup.remove_stale_ipv6.assert_called_once_with(
        ("2001:db8::20",),
    )
    cleanup.add_ipv6_addresses.assert_not_called()


def test_dry_run_reports_ipv6_delta_without_modifying_ipset() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()

    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=("dns-event",),
        cursor=SmartRoutingDnsLogCursor(10, 200),
        reset=False,
    )

    observer.parse_lines.return_value = (
        SmartRoutingDnsResponse(
            process_id=100,
            transaction_id="14",
            domain="example.com",
            ipv4_addresses=(),
            ipv6_addresses=("2001:db8::30",),
        ),
    )

    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=(),
        static_direct_ipv4_addresses=(),
        direct_ipv6_addresses=(),
    )

    result = coordinator.reconcile(
        direct_domains=("example.com",),
        cursor=SmartRoutingDnsLogCursor(10, 100),
        dry_run=True,
    )

    assert result.processed_responses == 1
    assert result.added_ipv6_addresses == ("2001:db8::30",)
    assert result.removed_ipv6_addresses == ()

    cleanup.add_ipv6_addresses.assert_not_called()
    cleanup.remove_stale_ipv6.assert_not_called()


def test_shared_ipv6_is_not_removed_while_another_domain_uses_it() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()

    coordinator._state_store.update(
        "two.example",
        ipv6_addresses=("2001:db8::40",),
    )

    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=("dns-event",),
        cursor=SmartRoutingDnsLogCursor(10, 200),
        reset=False,
    )

    observer.parse_lines.return_value = (
        SmartRoutingDnsResponse(
            process_id=100,
            transaction_id="15",
            domain="one.example",
            ipv4_addresses=(),
            ipv6_addresses=("2001:db8::50",),
        ),
    )

    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=(),
        static_direct_ipv4_addresses=(),
        direct_ipv6_addresses=("2001:db8::40",),
    )

    cleanup.add_ipv6_addresses.return_value = ("2001:db8::50",)

    result = coordinator.reconcile(
        direct_domains=("one.example", "two.example"),
        cursor=SmartRoutingDnsLogCursor(10, 100),
    )

    assert result.added_ipv6_addresses == ("2001:db8::50",)
    assert result.removed_ipv6_addresses == ()

    cleanup.add_ipv6_addresses.assert_called_once_with(
        ("2001:db8::50",),
    )
    cleanup.remove_stale_ipv6.assert_not_called()


def test_empty_applied_policy_cleans_dns_entries_and_preserves_static_ips() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()
    cursor = SmartRoutingDnsLogCursor(10, 300)
    reader.read.return_value = SmartRoutingDnsLogReadResult(
        lines=(),
        cursor=cursor,
        reset=False,
    )
    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=(
            "198.51.100.10",
            "198.51.100.20",
            "203.0.113.7",
        ),
        static_direct_ipv4_addresses=("203.0.113.7",),
        direct_ipv6_addresses=(),
        direct_domains=(),
        rendered_domains=(),
    )

    result = coordinator.reconcile(
        direct_domains=(),
        cursor=cursor,
        force_ipset_reconcile=True,
    )

    assert result.removed_ipv4_addresses == (
        "198.51.100.10",
        "198.51.100.20",
    )
    assert result.added_ipv4_addresses == ()
    cleanup.remove_stale.assert_called_once_with(
        ("198.51.100.10", "198.51.100.20"),
    )
    cleanup.remove_stale_ipv6.assert_not_called()


def test_full_reconcile_aborts_when_runtime_policy_changes() -> None:
    coordinator, reader, observer, runtime_state, cleanup = make_coordinator()
    cursor = SmartRoutingDnsLogCursor(10, 300)
    runtime_state.collect.return_value = Mock(
        direct_ipv4_addresses=("198.51.100.10",),
        static_direct_ipv4_addresses=(),
        direct_ipv6_addresses=(),
        direct_domains=("new.example",),
        rendered_domains=("new.example",),
    )

    with pytest.raises(
        RuntimeError,
        match="smart_routing_dns_full_reconcile_policy_changed",
    ):
        coordinator.reconcile(
            direct_domains=(),
            cursor=cursor,
            force_ipset_reconcile=True,
        )

    reader.read.assert_not_called()
    cleanup.remove_stale.assert_not_called()
    cleanup.add_addresses.assert_not_called()
