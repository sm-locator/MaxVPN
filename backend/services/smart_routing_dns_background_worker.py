from __future__ import annotations

import asyncio
import logging

from backend.services.smart_routing_dns_log_reader import (
    SmartRoutingDnsLogCursor,
)
from backend.services.smart_routing_dns_reconciliation_coordinator import (
    SmartRoutingDnsReconciliationCoordinator,
)
from backend.services.smart_routing_runtime_state import (
    SmartRoutingRuntimeStateCollector,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SmartRoutingDnsBackgroundWorker:
    """Long-lived DNS → DIRECT ipset reconciliation worker.

    In persistent mode, domain ownership is restored from PostgreSQL before
    log replay. The current log is replayed before pending deletions are applied,
    and only addresses with known ownership can enter the deletion outbox.
    """

    DEFAULT_INTERVAL_SECONDS = 2.0

    def __init__(
        self,
        coordinator: SmartRoutingDnsReconciliationCoordinator,
        runtime_state: SmartRoutingRuntimeStateCollector,
        *,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        persistent_state_enabled: bool = False,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero")

        self._coordinator = coordinator
        self._runtime_state = runtime_state
        self._interval_seconds = interval_seconds
        self._persistent_state_enabled = persistent_state_enabled
        self._persistent_state_initialized = not persistent_state_enabled
        self._stop_event = asyncio.Event()
        self._cursor: SmartRoutingDnsLogCursor | None = None
        self._bootstrapping = True
        self._bootstrap_log_available = False
        self._bootstrap_has_direct_responses = False
        self._allow_full_reconciliation = True
        self._needs_initial_reconciliation = False
        self._needs_initial_addition = False
        self._empty_direct_reconciled = False

    @property
    def cursor(self) -> SmartRoutingDnsLogCursor | None:
        return self._cursor

    async def run(self) -> None:
        logger.info("Smart Routing DNS background worker started")

        try:
            while not self._stop_event.is_set():
                if not self._persistent_state_initialized:
                    try:
                        await asyncio.to_thread(
                            self._coordinator.initialize_persistent_state,
                        )
                        self._persistent_state_initialized = True
                        logger.info(
                            "Smart Routing DNS persistent ownership restored "
                            "from PostgreSQL"
                        )
                    except Exception:
                        # A database outage must not start reconciliation with an
                        # empty ownership map. Retry initialization on the next cycle.
                        logger.exception(
                            "Smart Routing DNS persistent state initialization failed"
                        )
                        try:
                            await asyncio.wait_for(
                                self._stop_event.wait(),
                                timeout=self._interval_seconds,
                            )
                        except asyncio.TimeoutError:
                            pass
                        continue

                await self._run_cycle()

                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self._interval_seconds,
                    )
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            logger.info("Smart Routing DNS background worker cancelled")
            raise
        finally:
            logger.info("Smart Routing DNS background worker stopped")

    def _restart_bootstrap(
        self,
        current_cursor: SmartRoutingDnsLogCursor,
        *,
        clear_state: bool,
    ) -> None:
        if clear_state:
            self._coordinator.reset_state()
            # A rotated log no longer provides a complete ownership history.
            # Never run a global deletion diff from only the new log contents.
            self._allow_full_reconciliation = False
        self._cursor = SmartRoutingDnsLogCursor(current_cursor.inode, 0)
        self._bootstrapping = True
        self._bootstrap_log_available = current_cursor.inode != 0
        self._bootstrap_has_direct_responses = False
        self._needs_initial_reconciliation = False
        self._needs_initial_addition = False

    async def _run_cycle(self) -> None:
        try:
            runtime = await asyncio.to_thread(self._runtime_state.collect)
            direct_domains = tuple(sorted(set(runtime.direct_domains)))
            rendered_domains = tuple(sorted(set(runtime.rendered_domains)))

            # UCI describes the configured policy while dnsmasq's generated
            # files describe what is actually applied. Never reconcile a
            # changing domain set against a stale/inconsistent renderer state.
            if direct_domains != rendered_domains:
                self._empty_direct_reconciled = False
                logger.warning(
                    "Smart Routing DNS worker waiting for DNS config convergence: "
                    "uci_domains=%s rendered_domains=%s",
                    direct_domains,
                    rendered_domains,
                )
                return

            if not direct_domains:
                # In durable mode only addresses with known DNS ownership may be
                # removed. Unknown/legacy live ipset members are never swept.
                if self._empty_direct_reconciled:
                    if self._persistent_state_enabled:
                        await asyncio.to_thread(
                            self._coordinator.flush_pending_ipset_operations,
                            allow_deletions=True,
                        )
                    return

                cursor = self._cursor
                if cursor is None:
                    cursor = await asyncio.to_thread(
                        self._coordinator.current_cursor,
                    )

                reconcile_kwargs = {
                    "direct_domains": (),
                    "cursor": cursor,
                }
                if not self._persistent_state_enabled:
                    reconcile_kwargs["force_ipset_reconcile"] = True
                result = await asyncio.to_thread(
                    self._coordinator.reconcile,
                    **reconcile_kwargs,
                )
                self._cursor = result.cursor

                if result.log_reset:
                    self._restart_bootstrap(result.cursor, clear_state=True)
                    return

                self._empty_direct_reconciled = True
                self._bootstrapping = False
                self._needs_initial_reconciliation = False
                self._needs_initial_addition = False
                return

            self._empty_direct_reconciled = False

            if self._cursor is None:
                initial_cursor = await asyncio.to_thread(
                    self._coordinator.current_cursor,
                )
                self._restart_bootstrap(initial_cursor, clear_state=False)
                logger.info(
                    "Smart Routing DNS worker bootstrapping from log start: "
                    "inode=%d size=%d",
                    initial_cursor.inode,
                    initial_cursor.offset,
                )

            if self._bootstrapping:
                result = await asyncio.to_thread(
                    self._coordinator.reconcile,
                    direct_domains=direct_domains,
                    cursor=self._cursor,
                    dry_run=True,
                )
                self._cursor = result.cursor

                if result.log_reset:
                    self._restart_bootstrap(result.cursor, clear_state=True)
                    logger.info(
                        "Smart Routing DNS log changed during bootstrap; "
                        "restarting replay from offset zero",
                    )
                    return

                if result.processed_responses:
                    self._bootstrap_has_direct_responses = True

                latest_cursor = await asyncio.to_thread(
                    self._coordinator.current_cursor,
                )
                if (
                    self._cursor.inode != latest_cursor.inode
                    or self._cursor.offset > latest_cursor.offset
                ):
                    self._restart_bootstrap(latest_cursor, clear_state=True)
                    logger.info(
                        "Smart Routing DNS log rotated during bootstrap; "
                        "restarting replay from offset zero",
                    )
                    return

                caught_up = (
                    self._cursor.inode == latest_cursor.inode
                    and self._cursor.offset >= latest_cursor.offset
                )
                if not caught_up:
                    return

                self._bootstrapping = False
                self._needs_initial_reconciliation = (
                    not self._persistent_state_enabled
                    and self._allow_full_reconciliation
                    and self._bootstrap_log_available
                    and self._bootstrap_has_direct_responses
                )
                self._needs_initial_addition = (
                    not self._persistent_state_enabled
                    and self._bootstrap_has_direct_responses
                )
                logger.info(
                    "Smart Routing DNS worker bootstrap complete: "
                    "inode=%d offset=%d responses_seen=%s",
                    self._cursor.inode,
                    self._cursor.offset,
                    self._bootstrap_has_direct_responses,
                )

                # A full set diff is safe only after replaying the current log.
                # If the log was unavailable or had no DIRECT responses, do not
                # infer ownership for existing entries that we cannot explain.
                if self._persistent_state_enabled:
                    await asyncio.to_thread(
                        self._coordinator.flush_pending_ipset_operations,
                        allow_deletions=True,
                    )
                    return

                if (
                    not self._needs_initial_reconciliation
                    and not self._needs_initial_addition
                ):
                    return

            force_reconcile = self._needs_initial_reconciliation
            force_add_only = self._needs_initial_addition and not force_reconcile
            reconcile_kwargs = {
                "direct_domains": direct_domains,
                "cursor": self._cursor,
            }
            if force_reconcile:
                reconcile_kwargs["force_ipset_reconcile"] = True
            elif force_add_only:
                reconcile_kwargs["force_ipset_add_only"] = True
            result = await asyncio.to_thread(
                self._coordinator.reconcile,
                **reconcile_kwargs,
            )
            self._cursor = result.cursor

            if result.log_reset:
                self._restart_bootstrap(result.cursor, clear_state=True)
                logger.info(
                    "Smart Routing DNS log reset detected; restarting state replay",
                )
                return

            if force_reconcile:
                self._needs_initial_reconciliation = False
                self._needs_initial_addition = False
                self._allow_full_reconciliation = False
            elif force_add_only:
                self._needs_initial_addition = False

            if (
                result.processed_responses
                or result.added_ipv4_addresses
                or result.removed_ipv4_addresses
                or result.added_ipv6_addresses
                or result.removed_ipv6_addresses
            ):
                logger.info(
                    "Smart Routing DNS reconciliation: "
                    "processed=%d added=%s removed=%s "
                    "added_ipv6=%s removed_ipv6=%s reset=%s",
                    result.processed_responses,
                    result.added_ipv4_addresses,
                    result.removed_ipv4_addresses,
                    result.added_ipv6_addresses,
                    result.removed_ipv6_addresses,
                    result.log_reset,
                )

        except Exception:
            # A temporary SSH/OpenWrt/dnsmasq failure must not terminate the
            # worker or trigger speculative ipset cleanup.
            logger.exception("Smart Routing DNS background cycle failed")

    async def stop(self) -> None:
        self._stop_event.set()
