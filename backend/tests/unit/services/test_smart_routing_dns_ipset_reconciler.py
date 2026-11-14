from backend.services.smart_routing_dns_domain_state import (
    SmartRoutingDnsDomainStateStore,
)
from backend.services.smart_routing_dns_ipset_reconciler import (
    SmartRoutingDnsIpSetReconciler,
)


def test_first_dns_response_adds_missing_ip() -> None:
    store = SmartRoutingDnsDomainStateStore()
    store.update("example.com", ("1.1.1.1",))

    result = SmartRoutingDnsIpSetReconciler().build(
        store,
        (),
    )

    assert result.active_ipv4_addresses == ("1.1.1.1",)
    assert result.current_ipv4_addresses == ()
    assert result.addresses_to_add == ("1.1.1.1",)
    assert result.addresses_to_remove == ()


def test_existing_ip_is_kept() -> None:
    store = SmartRoutingDnsDomainStateStore()
    store.update("example.com", ("1.1.1.1",))

    result = SmartRoutingDnsIpSetReconciler().build(
        store,
        ("1.1.1.1",),
    )

    assert result.addresses_to_add == ()
    assert result.addresses_to_remove == ()


def test_dns_rollover_adds_new_and_removes_old() -> None:
    store = SmartRoutingDnsDomainStateStore()
    store.update("example.com", ("1.1.1.1",))
    store.update("example.com", ("2.2.2.2",))

    result = SmartRoutingDnsIpSetReconciler().build(
        store,
        ("1.1.1.1",),
    )

    assert result.addresses_to_add == ("2.2.2.2",)
    assert result.addresses_to_remove == ("1.1.1.1",)


def test_shared_ip_is_not_removed_while_another_domain_uses_it() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update("one.example", ("1.1.1.1",))
    store.update("two.example", ("1.1.1.1",))

    store.update("one.example", ("2.2.2.2",))

    result = SmartRoutingDnsIpSetReconciler().build(
        store,
        ("1.1.1.1",),
    )

    assert result.addresses_to_add == ("2.2.2.2",)
    assert result.addresses_to_remove == ()


def test_shared_ip_is_removed_after_all_domains_release_it() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update("one.example", ("1.1.1.1",))
    store.update("two.example", ("1.1.1.1",))

    store.update("one.example", ("2.2.2.2",))
    store.update("two.example", ("3.3.3.3",))

    result = SmartRoutingDnsIpSetReconciler().build(
        store,
        ("1.1.1.1",),
    )

    assert result.addresses_to_add == (
        "2.2.2.2",
        "3.3.3.3",
    )
    assert result.addresses_to_remove == ("1.1.1.1",)


def test_stale_ip_already_absent_from_ipset_is_not_removed() -> None:
    store = SmartRoutingDnsDomainStateStore()
    store.update("example.com", ("2.2.2.2",))

    result = SmartRoutingDnsIpSetReconciler().build(
        store,
        (),
    )

    assert result.addresses_to_add == ("2.2.2.2",)
    assert result.addresses_to_remove == ()


def test_empty_dns_state_removes_all_non_static_dns_entries() -> None:
    store = SmartRoutingDnsDomainStateStore()

    result = SmartRoutingDnsIpSetReconciler().build(
        store,
        (
            "1.1.1.1",
            "2.2.2.2",
        ),
    )

    assert result.active_ipv4_addresses == ()
    assert result.addresses_to_add == ()
    assert result.addresses_to_remove == (
        "1.1.1.1",
        "2.2.2.2",
    )


def test_duplicate_addresses_are_normalized() -> None:
    store = SmartRoutingDnsDomainStateStore()
    store.update(
        "example.com",
        (
            "1.1.1.1",
            "1.1.1.1",
            "2.2.2.2",
        ),
    )

    result = SmartRoutingDnsIpSetReconciler().build(
        store,
        (
            "1.1.1.1",
            "3.3.3.3",
            "3.3.3.3",
        ),
    )

    assert result.addresses_to_add == ("2.2.2.2",)
    assert result.addresses_to_remove == ("3.3.3.3",)


def test_result_is_deterministically_sorted() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update(
        "b.example",
        ("8.8.8.8", "1.1.1.1"),
    )
    store.update(
        "a.example",
        ("4.4.4.4", "2.2.2.2"),
    )

    result = SmartRoutingDnsIpSetReconciler().build(
        store,
        ("9.9.9.9", "1.1.1.1"),
    )

    assert result.active_ipv4_addresses == (
        "1.1.1.1",
        "2.2.2.2",
        "4.4.4.4",
        "8.8.8.8",
    )
    assert result.addresses_to_add == (
        "2.2.2.2",
        "4.4.4.4",
        "8.8.8.8",
    )
    assert result.addresses_to_remove == ("9.9.9.9",)


def test_first_dns_response_adds_missing_ipv6_address() -> None:
    store = SmartRoutingDnsDomainStateStore()
    store.update(
        "example.com",
        ipv6_addresses=("2001:db8::10",),
    )

    result = SmartRoutingDnsIpSetReconciler().build(
        store,
        (),
        (),
    )

    assert result.active_ipv6_addresses == ("2001:db8::10",)
    assert result.current_ipv6_addresses == ()
    assert result.ipv6_addresses_to_add == ("2001:db8::10",)
    assert result.ipv6_addresses_to_remove == ()


def test_ipv6_rollover_adds_new_and_removes_old() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update(
        "example.com",
        ipv6_addresses=("2001:db8::10",),
    )
    store.update(
        "example.com",
        ipv6_addresses=("2001:db8::11",),
    )

    result = SmartRoutingDnsIpSetReconciler().build(
        store,
        (),
        ("2001:db8::10",),
    )

    assert result.active_ipv6_addresses == ("2001:db8::11",)
    assert result.ipv6_addresses_to_add == ("2001:db8::11",)
    assert result.ipv6_addresses_to_remove == ("2001:db8::10",)


def test_shared_ipv6_is_not_removed_while_another_domain_uses_it() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update(
        "one.example",
        ipv6_addresses=("2001:db8::10",),
    )
    store.update(
        "two.example",
        ipv6_addresses=("2001:db8::10",),
    )

    store.update(
        "one.example",
        ipv6_addresses=("2001:db8::20",),
    )

    result = SmartRoutingDnsIpSetReconciler().build(
        store,
        (),
        ("2001:db8::10",),
    )

    assert result.active_ipv6_addresses == (
        "2001:db8::10",
        "2001:db8::20",
    )
    assert result.ipv6_addresses_to_add == ("2001:db8::20",)
    assert result.ipv6_addresses_to_remove == ()


def test_ipv6_is_removed_after_all_domains_release_it() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update(
        "one.example",
        ipv6_addresses=("2001:db8::10",),
    )
    store.update(
        "two.example",
        ipv6_addresses=("2001:db8::10",),
    )

    store.update(
        "one.example",
        ipv6_addresses=("2001:db8::20",),
    )
    store.update(
        "two.example",
        ipv6_addresses=("2001:db8::30",),
    )

    result = SmartRoutingDnsIpSetReconciler().build(
        store,
        (),
        ("2001:db8::10",),
    )

    assert result.active_ipv6_addresses == (
        "2001:db8::20",
        "2001:db8::30",
    )
    assert result.ipv6_addresses_to_add == (
        "2001:db8::20",
        "2001:db8::30",
    )
    assert result.ipv6_addresses_to_remove == ("2001:db8::10",)


def test_ipv4_reconciliation_does_not_affect_ipv6() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update(
        "example.com",
        ipv4_addresses=("192.0.2.10",),
        ipv6_addresses=("2001:db8::10",),
    )

    result = SmartRoutingDnsIpSetReconciler().build(
        store,
        ("192.0.2.10",),
        ("2001:db8::10",),
    )

    assert result.addresses_to_add == ()
    assert result.addresses_to_remove == ()
    assert result.ipv6_addresses_to_add == ()
    assert result.ipv6_addresses_to_remove == ()


def test_ipv6_reconciliation_does_not_affect_ipv4() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update(
        "example.com",
        ipv4_addresses=("192.0.2.10",),
        ipv6_addresses=("2001:db8::10",),
    )
    store.update(
        "example.com",
        ipv6_addresses=("2001:db8::11",),
    )

    result = SmartRoutingDnsIpSetReconciler().build(
        store,
        ("192.0.2.10",),
        ("2001:db8::10",),
    )

    assert result.addresses_to_add == ()
    assert result.addresses_to_remove == ()
    assert result.ipv6_addresses_to_add == ("2001:db8::11",)
    assert result.ipv6_addresses_to_remove == ("2001:db8::10",)


def test_empty_ipv6_state_removes_all_current_non_static_ipv6_addresses() -> None:
    store = SmartRoutingDnsDomainStateStore()

    result = SmartRoutingDnsIpSetReconciler().build(
        store,
        (),
        (
            "2001:db8::10",
            "2001:db8::20",
        ),
    )

    assert result.active_ipv6_addresses == ()
    assert result.ipv6_addresses_to_add == ()
    assert result.ipv6_addresses_to_remove == (
        "2001:db8::10",
        "2001:db8::20",
    )


def test_ipv6_result_is_deterministically_sorted() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update(
        "b.example",
        ipv6_addresses=("2001:db8::8", "2001:db8::1"),
    )
    store.update(
        "a.example",
        ipv6_addresses=("2001:db8::4", "2001:db8::2"),
    )

    result = SmartRoutingDnsIpSetReconciler().build(
        store,
        (),
        (
            "2001:db8::9",
            "2001:db8::1",
        ),
    )

    assert result.active_ipv6_addresses == (
        "2001:db8::1",
        "2001:db8::2",
        "2001:db8::4",
        "2001:db8::8",
    )
    assert result.ipv6_addresses_to_add == (
        "2001:db8::2",
        "2001:db8::4",
        "2001:db8::8",
    )
    assert result.ipv6_addresses_to_remove == ("2001:db8::9",)
