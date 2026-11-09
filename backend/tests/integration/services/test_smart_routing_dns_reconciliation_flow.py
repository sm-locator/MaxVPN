from unittest.mock import Mock, call

from backend.infrastructure.openwrt.openwrt_smart_routing_dns_cleanup import (
    OpenWrtSmartRoutingDnsCleanup,
)
from backend.models.command_result import CommandResult
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
from backend.services.smart_routing_dns_reconciliation_coordinator import (
    SmartRoutingDnsReconciliationCoordinator,
)
from backend.services.smart_routing_dns_response_observer import (
    SmartRoutingDnsResponseObserver,
)


def result(stdout: str = "", returncode: int = 0) -> CommandResult:
    return CommandResult(
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


class FakeRuntimeState:
    def __init__(self, addresses: tuple[str, ...]) -> None:
        self.addresses = addresses

    def collect(self):
        return Mock(
            direct_ipv4_addresses=self.addresses,
            static_direct_ipv4_addresses=(),
            direct_ipv6_addresses=(),
        )


def make_coordinator(
    *,
    reader_executor: Mock,
    runtime_state: FakeRuntimeState,
    cleanup_executor: Mock,
):
    reader = SmartRoutingDnsLogReader(reader_executor)
    observer = SmartRoutingDnsResponseObserver()
    store = SmartRoutingDnsDomainStateStore()
    reconciler = SmartRoutingDnsIpSetReconciler()
    cleanup = OpenWrtSmartRoutingDnsCleanup(cleanup_executor)

    coordinator = SmartRoutingDnsReconciliationCoordinator(
        log_reader=reader,
        response_observer=observer,
        state_store=store,
        ipset_reconciler=reconciler,
        runtime_state=runtime_state,
        cleanup=cleanup,
    )

    return coordinator, store


def test_full_dns_rollover_adds_new_and_removes_old_ip() -> None:
    first_log = (
        "Sep 12 01:00:00 dnsmasq[100]: "
        "11 127.0.0.1/10000 query[A] maxvpn-test.gps.navy "
        "from 127.0.0.1\n"
        "Sep 12 01:00:00 dnsmasq[100]: "
        "11 127.0.0.1/10000 reply maxvpn-test.gps.navy "
        "is 81.90.181.120\n"
    )

    second_log = (
        "Sep 12 01:01:00 dnsmasq[100]: "
        "12 127.0.0.1/10001 query[A] maxvpn-test.gps.navy "
        "from 127.0.0.1\n"
        "Sep 12 01:01:00 dnsmasq[100]: "
        "12 127.0.0.1/10001 reply maxvpn-test.gps.navy "
        "is 81.90.181.115\n"
    )

    reader_executor = Mock()
    reader_executor.run.side_effect = [
        result("5000 230\n"),
        result(first_log),
        result("5000 460\n"),
        result(second_log),
    ]

    runtime_state = FakeRuntimeState(())
    cleanup_executor = Mock()
    cleanup_executor.run.return_value = result()

    coordinator, store = make_coordinator(
        reader_executor=reader_executor,
        runtime_state=runtime_state,
        cleanup_executor=cleanup_executor,
    )

    first = coordinator.reconcile(
        direct_domains=("gps.navy",),
    )

    assert first.processed_responses == 1
    assert first.added_ipv4_addresses == ("81.90.181.120",)
    assert first.removed_ipv4_addresses == ()

    assert store.get("maxvpn-test.gps.navy").ipv4_addresses == ("81.90.181.120",)

    runtime_state.addresses = ("81.90.181.120",)

    second = coordinator.reconcile(
        direct_domains=("gps.navy",),
        cursor=first.cursor,
    )

    assert second.processed_responses == 1
    assert second.added_ipv4_addresses == ("81.90.181.115",)
    assert second.removed_ipv4_addresses == ("81.90.181.120",)

    assert store.get("maxvpn-test.gps.navy").ipv4_addresses == ("81.90.181.115",)

    assert cleanup_executor.run.call_args_list == [
        call(
            [
                "ipset",
                "add",
                "MAXVPN_DIRECT",
                "81.90.181.120",
                "-exist",
            ]
        ),
        call(
            [
                "ipset",
                "add",
                "MAXVPN_DIRECT",
                "81.90.181.115",
                "-exist",
            ]
        ),
        call(
            [
                "ipset",
                "del",
                "MAXVPN_DIRECT",
                "81.90.181.120",
            ]
        ),
    ]


def test_shared_ip_is_not_deleted_until_all_domains_release_it() -> None:
    first_log = (
        "Sep 12 02:00:00 dnsmasq[200]: "
        "21 127.0.0.1/10000 query[A] one.gps.navy "
        "from 127.0.0.1\n"
        "Sep 12 02:00:00 dnsmasq[200]: "
        "21 127.0.0.1/10000 reply one.gps.navy "
        "is 81.90.181.120\n"
        "Sep 12 02:00:00 dnsmasq[200]: "
        "22 127.0.0.1/10001 query[A] two.gps.navy "
        "from 127.0.0.1\n"
        "Sep 12 02:00:00 dnsmasq[200]: "
        "22 127.0.0.1/10001 reply two.gps.navy "
        "is 81.90.181.120\n"
    )

    second_log = (
        "Sep 12 02:01:00 dnsmasq[200]: "
        "23 127.0.0.1/10002 query[A] one.gps.navy "
        "from 127.0.0.1\n"
        "Sep 12 02:01:00 dnsmasq[200]: "
        "23 127.0.0.1/10002 reply one.gps.navy "
        "is 81.90.181.115\n"
    )

    reader_executor = Mock()
    reader_executor.run.side_effect = [
        result("6000 500\n"),
        result(first_log),
        result("6000 760\n"),
        result(second_log),
    ]

    runtime_state = FakeRuntimeState(())
    cleanup_executor = Mock()
    cleanup_executor.run.return_value = result()

    coordinator, store = make_coordinator(
        reader_executor=reader_executor,
        runtime_state=runtime_state,
        cleanup_executor=cleanup_executor,
    )

    first = coordinator.reconcile(
        direct_domains=("gps.navy",),
    )

    assert first.added_ipv4_addresses == ("81.90.181.120",)

    runtime_state.addresses = ("81.90.181.120",)

    second = coordinator.reconcile(
        direct_domains=("gps.navy",),
        cursor=first.cursor,
    )

    assert second.added_ipv4_addresses == ("81.90.181.115",)
    assert second.removed_ipv4_addresses == ()

    assert store.all_ipv4_addresses() == (
        "81.90.181.115",
        "81.90.181.120",
    )

    assert cleanup_executor.run.call_args_list == [
        call(
            [
                "ipset",
                "add",
                "MAXVPN_DIRECT",
                "81.90.181.120",
                "-exist",
            ]
        ),
        call(
            [
                "ipset",
                "add",
                "MAXVPN_DIRECT",
                "81.90.181.115",
                "-exist",
            ]
        ),
    ]


def test_unrelated_dns_events_advance_cursor_without_touching_runtime() -> None:
    log = (
        "Sep 12 02:10:00 dnsmasq[300]: "
        "31 127.0.0.1/10000 query[A] example.com "
        "from 127.0.0.1\n"
        "Sep 12 02:10:00 dnsmasq[300]: "
        "31 127.0.0.1/10000 reply example.com "
        "is 1.1.1.1\n"
    )

    reader_executor = Mock()
    reader_executor.run.side_effect = [
        result(f"7000 {len(log.encode())}\n"),
        result(log),
    ]

    cleanup_executor = Mock()

    coordinator, _ = make_coordinator(
        reader_executor=reader_executor,
        runtime_state=FakeRuntimeState(()),
        cleanup_executor=cleanup_executor,
    )

    result_value = coordinator.reconcile(
        direct_domains=("gps.navy",),
        cursor=SmartRoutingDnsLogCursor(7000, 0),
    )

    assert result_value.processed_responses == 0
    assert result_value.cursor == SmartRoutingDnsLogCursor(
        7000,
        len(log.encode()),
    )

    cleanup_executor.run.assert_not_called()


def test_removed_direct_domains_prune_dns_state_and_runtime_ips() -> None:
    reader_executor = Mock()
    reader_executor.run.side_effect = [
        result("9000 0\n"),
        result(""),
    ]

    runtime_state = FakeRuntimeState(
        (
            "91.236.49.2",
            "91.240.170.190",
        )
    )

    cleanup_executor = Mock()
    cleanup_executor.run.return_value = result()

    coordinator, store = make_coordinator(
        reader_executor=reader_executor,
        runtime_state=runtime_state,
        cleanup_executor=cleanup_executor,
    )

    store.update("maps.2gis.com", ("91.236.49.2",))
    store.update("photo.2gis.com", ("91.240.170.190",))

    reconciliation = coordinator.reconcile(
        direct_domains=(),
        cursor=SmartRoutingDnsLogCursor(9000, 0),
    )

    assert reconciliation.processed_responses == 0
    assert reconciliation.added_ipv4_addresses == ()
    assert reconciliation.removed_ipv4_addresses == (
        "91.236.49.2",
        "91.240.170.190",
    )
    assert store.all_ipv4_addresses() == ()

    cleanup_calls = cleanup_executor.run.call_args_list
    assert (
        call(
            [
                "ipset",
                "del",
                "MAXVPN_DIRECT",
                "91.236.49.2",
            ]
        )
        in cleanup_calls
    )
    assert (
        call(
            [
                "ipset",
                "del",
                "MAXVPN_DIRECT",
                "91.240.170.190",
            ]
        )
        in cleanup_calls
    )
