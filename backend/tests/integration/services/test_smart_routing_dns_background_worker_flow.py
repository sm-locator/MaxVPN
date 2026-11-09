from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from types import SimpleNamespace

from backend.infrastructure.openwrt.openwrt_smart_routing_dns_cleanup import (
    OpenWrtSmartRoutingDnsCleanup,
)
from backend.services.smart_routing_dns_background_worker import (
    SmartRoutingDnsBackgroundWorker,
)
from backend.services.smart_routing_dns_domain_state import (
    SmartRoutingDnsDomainState,
    SmartRoutingDnsDomainStateStore,
)
from backend.services.smart_routing_dns_ipset_reconciler import (
    SmartRoutingDnsIpSetReconciler,
)
from backend.services.smart_routing_dns_log_reader import SmartRoutingDnsLogReader
from backend.services.smart_routing_dns_reconciliation_coordinator import (
    SmartRoutingDnsReconciliationCoordinator,
)
from backend.services.smart_routing_dns_response_observer import (
    SmartRoutingDnsResponseObserver,
)


@dataclass(frozen=True)
class FakeCommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class MutableDnsLogExecutor:
    """In-memory stand-in for remote `stat`/`dd` calls used by the log reader."""

    def __init__(self, log: str, *, inode: int = 4242) -> None:
        self.log = log
        self.inode = inode
        self.commands: list[list[str]] = []

    def run(self, command: list[str]) -> FakeCommandResult:
        self.commands.append(command)
        script = command[-1]
        payload = self.log.encode("utf-8")

        if "dd if=" not in script:
            return FakeCommandResult(0, f"{self.inode} {len(payload)}\n")

        skip_match = re.search(r"\bskip=(\d+)", script)
        tail_match = re.search(r"tail -c \+(\d+)", script)
        head_match = re.search(r"head -c (\d+)", script)
        assert skip_match and tail_match and head_match, script
        start = int(skip_match.group(1)) * 4096 + int(tail_match.group(1)) - 1
        read_bytes = int(head_match.group(1))
        data = payload[start : start + read_bytes]
        return FakeCommandResult(0, data.decode("utf-8"))

    def append(self, log: str) -> None:
        self.log += log


class MutableIpSetExecutor:
    """Simulate ipset mutations while keeping DNS/static sets separate."""

    def __init__(self, direct: set[str], static: set[str]) -> None:
        self.sets = {
            "MAXVPN_DIRECT": set(direct),
            "MAXVPN_DIRECT_STATIC": set(static),
        }
        self.commands: list[list[str]] = []

    def run(self, command: list[str]) -> FakeCommandResult:
        self.commands.append(command)
        assert command[0:1] == ["ipset"], command
        action, set_name, address = command[1:4]
        target = self.sets.setdefault(set_name, set())
        if action == "add":
            target.add(address)
            return FakeCommandResult(0)
        if action == "del":
            if address not in target:
                return FakeCommandResult(1)
            target.remove(address)
            return FakeCommandResult(0)
        raise AssertionError(f"Unexpected command: {command!r}")


class MutableRuntimeState:
    def __init__(self, ipsets: MutableIpSetExecutor) -> None:
        self.ipsets = ipsets
        self.direct_domains = ("gps.navy",)

    def collect(self):
        dynamic = self.ipsets.sets["MAXVPN_DIRECT"]
        static = self.ipsets.sets["MAXVPN_DIRECT_STATIC"]
        return SimpleNamespace(
            direct_domains=self.direct_domains,
            rendered_domains=self.direct_domains,
            direct_ipv4_addresses=tuple(sorted(dynamic | static)),
            static_direct_ipv4_addresses=tuple(sorted(static)),
            direct_ipv6_addresses=(),
        )


def dns_response(transaction_id: int, timestamp: str, address: str) -> str:
    domain = "maxvpn-test.gps.navy"
    return (
        f"{timestamp} dnsmasq[100]: {transaction_id} 127.0.0.1/10000 "
        f"query[A] {domain} from 127.0.0.1\n"
        f"{timestamp} dnsmasq[100]: {transaction_id} 127.0.0.1/10000 "
        f"reply {domain} is {address}\n"
    )


def test_background_worker_applies_dns_ip_rollover_without_manual_apply() -> None:
    old_ip = "81.90.181.120"
    new_ip = "81.90.181.115"
    static_ip = "198.51.100.10"
    log_executor = MutableDnsLogExecutor(dns_response(11, "Oct 26 22:40:00", old_ip))
    ipset_executor = MutableIpSetExecutor({old_ip}, {static_ip})
    runtime = MutableRuntimeState(ipset_executor)

    coordinator = SmartRoutingDnsReconciliationCoordinator(
        log_reader=SmartRoutingDnsLogReader(log_executor),
        response_observer=SmartRoutingDnsResponseObserver(),
        state_store=SmartRoutingDnsDomainStateStore(),
        ipset_reconciler=SmartRoutingDnsIpSetReconciler(),
        runtime_state=runtime,
        cleanup=OpenWrtSmartRoutingDnsCleanup(ipset_executor),
    )
    worker = SmartRoutingDnsBackgroundWorker(
        coordinator=coordinator,
        runtime_state=runtime,
        interval_seconds=60,
    )

    # Bootstrap observes the old answer, then reconciles the current ipset.
    asyncio.run(worker._run_cycle())
    assert worker._bootstrapping is False
    assert ipset_executor.sets["MAXVPN_DIRECT"] == {old_ip}
    assert ipset_executor.sets["MAXVPN_DIRECT_STATIC"] == {static_ip}

    # A newer dnsmasq response rolls the domain to a different IP. The regular
    # worker cycle must add the new address and remove the previously owned IP.
    log_executor.append(dns_response(12, "Oct 26 22:41:00", new_ip))
    before = len(ipset_executor.commands)
    asyncio.run(worker._run_cycle())

    assert ipset_executor.sets["MAXVPN_DIRECT"] == {new_ip}
    assert old_ip not in ipset_executor.sets["MAXVPN_DIRECT"]
    assert ipset_executor.sets["MAXVPN_DIRECT_STATIC"] == {static_ip}
    assert ipset_executor.commands[before:] == [
        ["ipset", "add", "MAXVPN_DIRECT", new_ip, "-exist"],
        ["ipset", "del", "MAXVPN_DIRECT", old_ip],
    ]
    assert worker.cursor is not None
    assert worker.cursor.offset == len(log_executor.log.encode("utf-8"))


@dataclass(frozen=True)
class FakeDnsOutboxOperation:
    address_family: str
    address: str
    desired_present: bool


class MutableDnsStateRepository:
    """In-memory implementation of the persistent DNS repository contract."""

    def __init__(self, states=()):
        self.states = tuple(states)
        self.pending = {}
        self.fail_ack_once = False

    def load_domain_states(self):
        return self.states

    def _upsert(self, family, address, desired_present):
        self.pending[(family, address)] = FakeDnsOutboxOperation(
            family,
            address,
            desired_present,
        )

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
        self.states = tuple(domain_states)

        for address in added_ipv4_addresses:
            self._upsert("ipv4", address, True)
        for address in added_ipv6_addresses:
            self._upsert("ipv6", address, True)
        for address in removed_ipv4_addresses:
            self._upsert("ipv4", address, False)
        for address in removed_ipv6_addresses:
            self._upsert("ipv6", address, False)

    def list_pending_operations(self):
        return tuple(
            sorted(
                self.pending.values(),
                key=lambda operation: (
                    not operation.desired_present,
                    operation.address_family,
                    operation.address,
                ),
            )
        )

    def acknowledge_operation(self, operation):
        if self.fail_ack_once:
            self.fail_ack_once = False
            raise RuntimeError("simulated database acknowledgement failure")

        key = (operation.address_family, operation.address)
        if self.pending.get(key) != operation:
            return False
        del self.pending[key]
        return True


def test_persistent_worker_replays_rotated_dns_log_without_losing_ownership():
    old_ip = "81.90.181.120"
    new_ip = "81.90.181.115"
    unknown_ip = "198.51.100.99"
    static_ip = "198.51.100.10"
    domain = "maxvpn-test.gps.navy"

    old_state = SmartRoutingDnsDomainState(domain, (old_ip,))
    repository = MutableDnsStateRepository((old_state,))

    log_executor = MutableDnsLogExecutor("", inode=4242)
    ipset_executor = MutableIpSetExecutor(
        {old_ip, unknown_ip},
        {static_ip},
    )
    runtime = MutableRuntimeState(ipset_executor)
    state_store = SmartRoutingDnsDomainStateStore()

    coordinator = SmartRoutingDnsReconciliationCoordinator(
        log_reader=SmartRoutingDnsLogReader(log_executor),
        response_observer=SmartRoutingDnsResponseObserver(),
        state_store=state_store,
        ipset_reconciler=SmartRoutingDnsIpSetReconciler(),
        runtime_state=runtime,
        cleanup=OpenWrtSmartRoutingDnsCleanup(ipset_executor),
        state_repository=repository,
    )

    # Restore durable ownership before the worker starts processing the log.
    coordinator.initialize_persistent_state()

    worker = SmartRoutingDnsBackgroundWorker(
        coordinator=coordinator,
        runtime_state=runtime,
        interval_seconds=60,
        persistent_state_enabled=True,
    )

    # Initial bootstrap: the persisted address is already present in ipset.
    asyncio.run(worker._run_cycle())

    assert worker._bootstrapping is False
    assert worker.cursor is not None
    assert worker.cursor.inode == 4242
    assert state_store.get(domain) == old_state
    assert repository.pending == {}
    assert ipset_executor.commands == []

    # Simulate DNS log rotation: the new inode contains a new answer
    # for the previously owned domain.
    log_executor.log = dns_response(
        12,
        "Oct 30 22:41:00",
        new_ip,
    )
    log_executor.inode = 4343

    asyncio.run(worker._run_cycle())

    # The inode change restarts bootstrap at offset zero.
    # Persistent ownership must survive coordinator.reset_state().
    assert worker._bootstrapping is True
    assert worker.cursor is not None
    assert worker.cursor.inode == 4343
    assert worker.cursor.offset == 0
    assert state_store.get(domain) == old_state
    assert repository.states == (old_state,)
    assert ipset_executor.commands == []

    # Replay the new log from offset zero. The coordinator persists the
    # new ownership and its ADD/DELETE intents before the worker flushes them.
    asyncio.run(worker._run_cycle())

    new_state = SmartRoutingDnsDomainState(domain, (new_ip,))

    assert worker._bootstrapping is False
    assert worker.cursor is not None
    assert worker.cursor.inode == 4343
    assert worker.cursor.offset == len(log_executor.log.encode("utf-8"))

    assert state_store.get(domain) == new_state
    assert repository.states == (new_state,)
    assert repository.pending == {}

    # ADD must happen before DELETE. Unknown and static entries are preserved.
    assert ipset_executor.commands == [
        ["ipset", "add", "MAXVPN_DIRECT", new_ip, "-exist"],
        ["ipset", "del", "MAXVPN_DIRECT", old_ip],
    ]
    assert ipset_executor.sets["MAXVPN_DIRECT"] == {
        new_ip,
        unknown_ip,
    }
    assert ipset_executor.sets["MAXVPN_DIRECT_STATIC"] == {static_ip}


def test_persistent_ipset_add_is_not_repeated_when_repository_ack_fails():
    owned_ip = "81.90.181.120"
    unknown_ip = "198.51.100.99"
    static_ip = "198.51.100.10"
    domain = "maxvpn-test.gps.navy"

    state = SmartRoutingDnsDomainState(domain, (owned_ip,))
    repository = MutableDnsStateRepository((state,))
    repository.fail_ack_once = True

    ipset_executor = MutableIpSetExecutor(
        {unknown_ip},
        {static_ip},
    )
    runtime = MutableRuntimeState(ipset_executor)

    coordinator = SmartRoutingDnsReconciliationCoordinator(
        log_reader=SmartRoutingDnsLogReader(MutableDnsLogExecutor("", inode=4242)),
        response_observer=SmartRoutingDnsResponseObserver(),
        state_store=SmartRoutingDnsDomainStateStore(),
        ipset_reconciler=SmartRoutingDnsIpSetReconciler(),
        runtime_state=runtime,
        cleanup=OpenWrtSmartRoutingDnsCleanup(ipset_executor),
        state_repository=repository,
    )
    coordinator.initialize_persistent_state()

    # The ipset command succeeds, but the database acknowledgement fails.
    try:
        coordinator.flush_pending_ipset_operations()
    except RuntimeError as exc:
        assert str(exc) == "simulated database acknowledgement failure"
    else:
        raise AssertionError("Expected simulated acknowledgement failure")

    assert ipset_executor.sets["MAXVPN_DIRECT"] == {
        owned_ip,
        unknown_ip,
    }
    assert repository.pending[("ipv4", owned_ip)].desired_present is True
    assert repository.states == (state,)

    expected_command = [
        "ipset",
        "add",
        "MAXVPN_DIRECT",
        owned_ip,
        "-exist",
    ]
    assert ipset_executor.commands == [expected_command]

    # Retry sees that the address is already live and acknowledges the
    # durable intent without executing the successful ADD command again.
    result = coordinator.flush_pending_ipset_operations()

    assert result == ((), (), (), ())
    assert repository.pending == {}
    assert ipset_executor.commands == [expected_command]

    # Unrelated and static members remain untouched.
    assert ipset_executor.sets["MAXVPN_DIRECT"] == {
        owned_ip,
        unknown_ip,
    }
    assert ipset_executor.sets["MAXVPN_DIRECT_STATIC"] == {static_ip}
