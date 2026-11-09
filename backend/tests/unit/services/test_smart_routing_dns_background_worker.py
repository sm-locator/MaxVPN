import asyncio
from unittest.mock import Mock, call

from backend.services.smart_routing_dns_background_worker import (
    SmartRoutingDnsBackgroundWorker,
)
from backend.services.smart_routing_dns_log_reader import (
    SmartRoutingDnsLogCursor,
)


def make_runtime(domains=()):
    runtime = Mock()
    runtime.collect.return_value = Mock(
        direct_domains=tuple(domains),
        rendered_domains=tuple(domains),
    )
    return runtime


def result(*, cursor, processed=0, added=(), removed=(), reset=False):
    return Mock(
        processed_responses=processed,
        added_ipv4_addresses=added,
        removed_ipv4_addresses=removed,
        added_ipv6_addresses=(),
        removed_ipv6_addresses=(),
        cursor=cursor,
        log_reset=reset,
    )


def test_worker_replays_existing_dns_log_before_full_reconciliation():
    coordinator = Mock()
    end = SmartRoutingDnsLogCursor(100, 200)
    coordinator.current_cursor.return_value = end
    coordinator.reconcile.side_effect = [
        result(cursor=end, processed=1, added=("81.90.181.120",)),
        result(cursor=end),
    ]

    runtime = make_runtime(("gps.navy", "example.gps.navy"))
    worker = SmartRoutingDnsBackgroundWorker(
        coordinator=coordinator,
        runtime_state=runtime,
        interval_seconds=60,
    )

    asyncio.run(worker._run_cycle())

    expected_domains = ("example.gps.navy", "gps.navy")
    assert coordinator.current_cursor.call_count == 2
    assert coordinator.reconcile.call_args_list == [
        call(
            direct_domains=expected_domains,
            cursor=SmartRoutingDnsLogCursor(100, 0),
            dry_run=True,
        ),
        call(
            direct_domains=expected_domains,
            cursor=end,
            force_ipset_reconcile=True,
        ),
    ]
    assert worker.cursor == end
    assert worker._bootstrapping is False
    assert worker._needs_initial_reconciliation is False


def test_worker_processes_large_log_in_chunks_before_cleanup():
    coordinator = Mock()
    end = SmartRoutingDnsLogCursor(100, 500_000)
    coordinator.current_cursor.return_value = end
    coordinator.reconcile.side_effect = [
        result(cursor=SmartRoutingDnsLogCursor(100, 250_000), processed=1),
        result(cursor=end, processed=1),
        result(cursor=end),
    ]

    worker = SmartRoutingDnsBackgroundWorker(
        coordinator=coordinator,
        runtime_state=make_runtime(("gps.navy",)),
        interval_seconds=60,
    )

    asyncio.run(worker._run_cycle())
    assert worker._bootstrapping is True
    assert coordinator.reconcile.call_count == 1

    asyncio.run(worker._run_cycle())
    assert coordinator.reconcile.call_count == 3
    assert coordinator.reconcile.call_args_list[0] == call(
        direct_domains=("gps.navy",),
        cursor=SmartRoutingDnsLogCursor(100, 0),
        dry_run=True,
    )
    assert coordinator.reconcile.call_args_list[1] == call(
        direct_domains=("gps.navy",),
        cursor=SmartRoutingDnsLogCursor(100, 250_000),
        dry_run=True,
    )
    assert coordinator.reconcile.call_args_list[2] == call(
        direct_domains=("gps.navy",),
        cursor=end,
        force_ipset_reconcile=True,
    )
    assert worker._bootstrapping is False
    assert worker.cursor == end


def test_worker_restarts_bootstrap_after_log_reset():
    coordinator = Mock()
    initial = SmartRoutingDnsLogCursor(100, 100)
    reset_cursor = SmartRoutingDnsLogCursor(200, 50)
    coordinator.current_cursor.return_value = initial
    coordinator.reconcile.side_effect = [result(cursor=reset_cursor, reset=True)]

    worker = SmartRoutingDnsBackgroundWorker(
        coordinator=coordinator,
        runtime_state=make_runtime(("gps.navy",)),
        interval_seconds=60,
    )

    asyncio.run(worker._run_cycle())

    coordinator.reset_state.assert_called_once_with()
    assert worker.cursor == SmartRoutingDnsLogCursor(200, 0)
    assert worker._bootstrapping is True
    assert worker._needs_initial_reconciliation is False


def test_worker_uses_add_only_sync_after_observed_log_reset():
    coordinator = Mock()
    initial = SmartRoutingDnsLogCursor(100, 100)
    reset_cursor = SmartRoutingDnsLogCursor(200, 50)
    end = SmartRoutingDnsLogCursor(200, 300)
    coordinator.current_cursor.side_effect = [initial, end]
    coordinator.reconcile.side_effect = [
        result(cursor=reset_cursor, reset=True),
        result(cursor=end, processed=1, added=("198.51.100.20",)),
        result(cursor=end, added=("198.51.100.20",)),
    ]

    worker = SmartRoutingDnsBackgroundWorker(
        coordinator=coordinator,
        runtime_state=make_runtime(("example.com",)),
        interval_seconds=60,
    )

    asyncio.run(worker._run_cycle())
    assert worker._allow_full_reconciliation is False
    assert worker._bootstrapping is True

    asyncio.run(worker._run_cycle())
    assert worker._bootstrapping is False
    assert coordinator.reconcile.call_args_list[1] == call(
        direct_domains=("example.com",),
        cursor=SmartRoutingDnsLogCursor(200, 0),
        dry_run=True,
    )
    assert coordinator.reconcile.call_args_list[2] == call(
        direct_domains=("example.com",),
        cursor=end,
        force_ipset_add_only=True,
    )
    assert worker._needs_initial_addition is False


def test_worker_cleans_stale_dns_entries_when_no_direct_domains_remain():
    coordinator = Mock()
    cursor = SmartRoutingDnsLogCursor(100, 200)
    coordinator.current_cursor.return_value = cursor
    coordinator.reconcile.return_value = result(cursor=cursor)

    worker = SmartRoutingDnsBackgroundWorker(
        coordinator=coordinator,
        runtime_state=make_runtime(()),
        interval_seconds=60,
    )

    asyncio.run(worker._run_cycle())

    coordinator.current_cursor.assert_called_once_with()
    coordinator.reconcile.assert_called_once_with(
        direct_domains=(),
        cursor=cursor,
        force_ipset_reconcile=True,
    )
    assert worker._empty_direct_reconciled is True
    assert worker.cursor == cursor

    # Do not issue the same full diff on every two-second worker cycle.
    asyncio.run(worker._run_cycle())
    coordinator.reconcile.assert_called_once()


def test_worker_waits_until_uci_and_rendered_domains_match():
    coordinator = Mock()
    runtime = make_runtime(())
    runtime.collect.return_value = Mock(
        direct_domains=(),
        rendered_domains=("still-applied.example",),
    )
    worker = SmartRoutingDnsBackgroundWorker(
        coordinator=coordinator,
        runtime_state=runtime,
        interval_seconds=60,
    )

    asyncio.run(worker._run_cycle())

    coordinator.current_cursor.assert_not_called()
    coordinator.reconcile.assert_not_called()
    assert worker._empty_direct_reconciled is False


def test_worker_survives_runtime_state_failure():
    coordinator = Mock()
    runtime = Mock()
    runtime.collect.side_effect = RuntimeError("temporary SSH failure")

    worker = SmartRoutingDnsBackgroundWorker(
        coordinator=coordinator,
        runtime_state=runtime,
        interval_seconds=60,
    )

    asyncio.run(worker._run_cycle())

    coordinator.reconcile.assert_not_called()
    assert worker.cursor is None


def test_stop_releases_waiting_worker():
    coordinator = Mock()
    runtime = make_runtime(("gps.navy",))
    end = SmartRoutingDnsLogCursor(100, 0)
    coordinator.current_cursor.return_value = end
    coordinator.reconcile.return_value = result(cursor=end)

    worker = SmartRoutingDnsBackgroundWorker(
        coordinator=coordinator,
        runtime_state=runtime,
        interval_seconds=3600,
    )

    async def run_worker():
        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0.01)
        await worker.stop()
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(run_worker())


def test_persistent_worker_never_uses_global_full_diff_for_empty_policy():
    coordinator = Mock()
    cursor = SmartRoutingDnsLogCursor(100, 200)
    coordinator.current_cursor.return_value = cursor
    coordinator.reconcile.return_value = result(cursor=cursor)

    worker = SmartRoutingDnsBackgroundWorker(
        coordinator=coordinator,
        runtime_state=make_runtime(()),
        interval_seconds=60,
        persistent_state_enabled=True,
    )

    asyncio.run(worker._run_cycle())

    coordinator.reconcile.assert_called_once_with(
        direct_domains=(),
        cursor=cursor,
    )


def test_persistent_worker_flushes_after_current_log_bootstrap_without_full_diff():
    coordinator = Mock()
    cursor = SmartRoutingDnsLogCursor(100, 200)
    coordinator.current_cursor.return_value = cursor
    coordinator.reconcile.return_value = result(
        cursor=cursor,
        processed=1,
        added=("192.0.2.10",),
    )

    worker = SmartRoutingDnsBackgroundWorker(
        coordinator=coordinator,
        runtime_state=make_runtime(("example.com",)),
        interval_seconds=60,
        persistent_state_enabled=True,
    )

    asyncio.run(worker._run_cycle())

    coordinator.reconcile.assert_called_once_with(
        direct_domains=("example.com",),
        cursor=SmartRoutingDnsLogCursor(100, 0),
        dry_run=True,
    )
    coordinator.flush_pending_ipset_operations.assert_called_once_with(
        allow_deletions=True,
    )
