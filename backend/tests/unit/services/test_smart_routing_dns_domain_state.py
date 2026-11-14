from backend.services.smart_routing_dns_domain_state import (
    SmartRoutingDnsDomainState,
    SmartRoutingDnsDomainStateStore,
)


def test_first_response_adds_all_addresses() -> None:
    store = SmartRoutingDnsDomainStateStore()

    update = store.update(
        "maxvpn-test.gps.navy",
        ("81.90.181.120", "81.90.181.115"),
    )

    assert update.domain == "maxvpn-test.gps.navy"
    assert update.previous_ipv4_addresses == ()
    assert update.current_ipv4_addresses == (
        "81.90.181.115",
        "81.90.181.120",
    )
    assert update.added_ipv4_addresses == (
        "81.90.181.115",
        "81.90.181.120",
    )
    assert update.removed_ipv4_addresses == ()
    assert update.changed is True


def test_same_response_is_idempotent() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update(
        "example.com",
        ("1.1.1.1", "2.2.2.2"),
    )

    update = store.update(
        "example.com.",
        ("2.2.2.2", "1.1.1.1"),
    )

    assert update.previous_ipv4_addresses == (
        "1.1.1.1",
        "2.2.2.2",
    )
    assert update.current_ipv4_addresses == (
        "1.1.1.1",
        "2.2.2.2",
    )
    assert update.added_ipv4_addresses == ()
    assert update.removed_ipv4_addresses == ()
    assert update.changed is False


def test_rollover_detects_added_and_removed_addresses() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update(
        "maxvpn-test.gps.navy",
        ("81.90.181.103",),
    )

    update = store.update(
        "maxvpn-test.gps.navy",
        ("81.90.181.115",),
    )

    assert update.added_ipv4_addresses == ("81.90.181.115",)
    assert update.removed_ipv4_addresses == ("81.90.181.103",)
    assert update.current_ipv4_addresses == ("81.90.181.115",)


def test_multiple_addresses_can_overlap_during_rollover() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update(
        "example.com",
        ("1.1.1.1", "2.2.2.2"),
    )

    update = store.update(
        "example.com",
        ("2.2.2.2", "3.3.3.3"),
    )

    assert update.added_ipv4_addresses == ("3.3.3.3",)
    assert update.removed_ipv4_addresses == ("1.1.1.1",)


def test_empty_successful_response_removes_previous_addresses() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update(
        "example.com",
        ("1.1.1.1",),
    )

    update = store.update("example.com", ())

    assert update.current_ipv4_addresses == ()
    assert update.removed_ipv4_addresses == ("1.1.1.1",)
    assert update.changed is True


def test_failed_dns_request_is_not_represented_by_update() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update(
        "example.com",
        ("1.1.1.1",),
    )

    # The store is only called for successful DNS responses.
    # Therefore a failed DNS query leaves the previous state intact.
    state = store.get("example.com")

    assert state is not None
    assert state.ipv4_addresses == ("1.1.1.1",)


def test_one_ip_shared_by_two_domains_remains_in_union() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update("one.example", ("1.1.1.1",))
    store.update("two.example", ("1.1.1.1",))

    store.update("one.example", ("2.2.2.2",))

    assert store.all_ipv4_addresses() == (
        "1.1.1.1",
        "2.2.2.2",
    )


def test_remove_domain_returns_its_previous_addresses() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update("example.com", ("1.1.1.1", "2.2.2.2"))

    update = store.remove("example.com")

    assert update is not None
    assert update.removed_ipv4_addresses == (
        "1.1.1.1",
        "2.2.2.2",
    )
    assert store.get("example.com") is None


def test_all_states_are_sorted_by_domain() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update("z.example", ("3.3.3.3",))
    store.update("a.example", ("1.1.1.1",))

    assert [state.domain for state in store.all_states()] == [
        "a.example",
        "z.example",
    ]


def test_domain_is_normalized() -> None:
    store = SmartRoutingDnsDomainStateStore()

    update = store.update(
        " Example.COM. ",
        ("1.1.1.1",),
    )

    assert update.domain == "example.com"
    assert store.get("EXAMPLE.COM") is not None


def test_prune_to_domains_removes_states_for_removed_direct_domains() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update("maps.2gis.com", ("91.236.49.2",))
    store.update("photo.2gis.com", ("91.240.170.190",))
    store.update("2gis.ru", ("5.188.34.0",))

    removed = store.prune_to_domains(("2gis.ru",))

    assert removed == ("91.236.49.2", "91.240.170.190")
    assert store.get("maps.2gis.com") is None
    assert store.get("photo.2gis.com") is None
    assert store.get("2gis.ru") is not None
    assert store.all_ipv4_addresses() == ("5.188.34.0",)


def test_first_response_adds_ipv6_addresses() -> None:
    store = SmartRoutingDnsDomainStateStore()

    update = store.update(
        "ipv6.example",
        ipv6_addresses=("2001:db8::10", "2001:db8::11"),
    )

    assert update.domain == "ipv6.example"
    assert update.previous_ipv6_addresses == ()
    assert update.current_ipv6_addresses == (
        "2001:db8::10",
        "2001:db8::11",
    )
    assert update.added_ipv6_addresses == (
        "2001:db8::10",
        "2001:db8::11",
    )
    assert update.removed_ipv6_addresses == ()
    assert update.changed is True


def test_ipv4_refresh_does_not_erase_ipv6_state() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update(
        "example.com",
        ipv4_addresses=("192.0.2.10",),
        ipv6_addresses=("2001:db8::10",),
    )

    update = store.update(
        "example.com",
        ipv4_addresses=("192.0.2.11",),
    )

    assert update.previous_ipv4_addresses == ("192.0.2.10",)
    assert update.current_ipv4_addresses == ("192.0.2.11",)
    assert update.current_ipv6_addresses == ("2001:db8::10",)

    assert update.added_ipv4_addresses == ("192.0.2.11",)
    assert update.removed_ipv4_addresses == ("192.0.2.10",)
    assert update.added_ipv6_addresses == ()
    assert update.removed_ipv6_addresses == ()


def test_ipv6_refresh_does_not_erase_ipv4_state() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update(
        "example.com",
        ipv4_addresses=("192.0.2.10",),
        ipv6_addresses=("2001:db8::10",),
    )

    update = store.update(
        "example.com",
        ipv6_addresses=("2001:db8::11",),
    )

    assert update.current_ipv4_addresses == ("192.0.2.10",)
    assert update.current_ipv6_addresses == ("2001:db8::11",)

    assert update.added_ipv4_addresses == ()
    assert update.removed_ipv4_addresses == ()
    assert update.added_ipv6_addresses == ("2001:db8::11",)
    assert update.removed_ipv6_addresses == ("2001:db8::10",)


def test_ipv6_rollover_detects_added_and_removed_addresses() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update(
        "example.com",
        ipv6_addresses=("2001:db8::10",),
    )

    update = store.update(
        "example.com",
        ipv6_addresses=("2001:db8::11",),
    )

    assert update.added_ipv6_addresses == ("2001:db8::11",)
    assert update.removed_ipv6_addresses == ("2001:db8::10",)
    assert update.current_ipv6_addresses == ("2001:db8::11",)


def test_remove_domain_removes_both_address_families() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update(
        "example.com",
        ipv4_addresses=("192.0.2.10",),
        ipv6_addresses=("2001:db8::10", "2001:db8::11"),
    )

    update = store.remove("example.com")

    assert update is not None
    assert update.removed_ipv4_addresses == ("192.0.2.10",)
    assert update.removed_ipv6_addresses == (
        "2001:db8::10",
        "2001:db8::11",
    )
    assert store.get("example.com") is None
    assert store.all_ipv4_addresses() == ()
    assert store.all_ipv6_addresses() == ()


def test_prune_to_domains_removes_ipv6_from_removed_domains() -> None:
    store = SmartRoutingDnsDomainStateStore()

    store.update(
        "keep.example",
        ipv4_addresses=("192.0.2.10",),
        ipv6_addresses=("2001:db8::10",),
    )
    store.update(
        "remove.example",
        ipv4_addresses=("192.0.2.20",),
        ipv6_addresses=("2001:db8::20",),
    )

    removed_ipv4 = store.prune_to_domains(("keep.example",))

    assert removed_ipv4 == ("192.0.2.20",)
    assert store.get("remove.example") is None
    assert store.all_ipv4_addresses() == ("192.0.2.10",)
    assert store.all_ipv6_addresses() == ("2001:db8::10",)


def test_replace_all_replaces_snapshot_and_normalizes_domains() -> None:
    store = SmartRoutingDnsDomainStateStore()
    store.update("old.example", ("192.0.2.1",))

    store.replace_all(
        (
            SmartRoutingDnsDomainState(
                " Example.COM. ",
                ("192.0.2.10", "192.0.2.10"),
                ("2001:db8::10",),
            ),
        )
    )

    assert [state.domain for state in store.all_states()] == ["example.com"]
    assert store.all_ipv4_addresses() == ("192.0.2.10",)
    assert store.all_ipv6_addresses() == ("2001:db8::10",)
