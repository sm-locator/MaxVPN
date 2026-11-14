from backend.services.smart_routing_runtime_diff import (
    SmartRoutingRuntimeDiffService,
)
from backend.services.smart_routing_runtime_preview import (
    SmartRoutingRuntimePreview,
)
from backend.services.smart_routing_runtime_state import (
    SmartRoutingRuntimeState,
)


def make_state(
    *,
    ips=(),
    static_ips=None,
    domains=(),
):
    if static_ips is None:
        static_ips = ips

    return SmartRoutingRuntimeState(
        direct_ipv4_addresses=tuple(ips),
        static_direct_ipv4_addresses=tuple(static_ips),
        direct_domains=tuple(domains),
        rendered_domains=tuple(domains),
        policy_rules=(),
        routing_table_200=(),
    )


def make_preview(
    *,
    networks=(),
    domains=(),
):
    return SmartRoutingRuntimePreview(
        direct_ipv4_networks=tuple(networks),
        direct_domains=tuple(domains),
    )


def test_ipv4_addresses_are_compared_by_network_coverage() -> None:
    current = make_state(
        ips=("192.0.2.10", "192.0.2.20", "198.51.100.10"),
    )
    desired = make_preview(
        networks=("192.0.2.0/24",),
    )

    diff = SmartRoutingRuntimeDiffService().build(current, desired)

    assert diff.covered_ipv4_addresses == (
        "192.0.2.10",
        "192.0.2.20",
    )
    assert diff.stale_ipv4_addresses == ("198.51.100.10",)
    assert diff.ipv4_replace_required is True


def test_ipv4_runtime_is_unchanged_when_all_current_addresses_are_covered() -> None:
    current = make_state(
        ips=("192.0.2.10", "192.0.2.20"),
    )
    desired = make_preview(
        networks=("192.0.2.0/24",),
    )

    diff = SmartRoutingRuntimeDiffService().build(current, desired)

    assert diff.ipv4_replace_required is False
    assert diff.stale_ipv4_addresses == ()


def test_ipv4_runtime_changes_when_desired_contains_additional_network() -> None:
    current = make_state(
        ips=("192.0.2.10", "192.0.2.20"),
    )
    desired = make_preview(
        networks=("192.0.2.0/24", "198.51.100.0/24"),
    )

    diff = SmartRoutingRuntimeDiffService().build(current, desired)

    assert diff.ipv4_replace_required is True
    assert diff.covered_ipv4_addresses == (
        "192.0.2.10",
        "192.0.2.20",
    )
    assert diff.stale_ipv4_addresses == ()


def test_empty_current_ipv4_requires_apply_when_desired_is_non_empty() -> None:
    current = make_state()
    desired = make_preview(
        networks=("192.0.2.10/32",),
    )

    diff = SmartRoutingRuntimeDiffService().build(current, desired)

    assert diff.ipv4_replace_required is True
    assert diff.covered_ipv4_addresses == ()
    assert diff.stale_ipv4_addresses == ()
    assert diff.has_changes is True


def test_domain_diff_is_exact() -> None:
    current = make_state(
        domains=("example.com", "old.example"),
    )
    desired = make_preview(
        domains=("example.com", "new.example"),
    )

    diff = SmartRoutingRuntimeDiffService().build(current, desired)

    assert diff.added_domains == ("new.example",)
    assert diff.removed_domains == ("old.example",)
    assert diff.unchanged_domains == ("example.com",)


def test_empty_desired_ipv4_requires_flush_when_current_has_members() -> None:
    current = make_state(
        ips=("192.0.2.10",),
    )
    desired = make_preview()

    diff = SmartRoutingRuntimeDiffService().build(current, desired)

    assert diff.ipv4_replace_required is True
    assert diff.stale_ipv4_addresses == ("192.0.2.10",)
    assert diff.has_changes is True


def test_dns_derived_ipv4_addresses_are_not_stale_when_direct_domains_are_active() -> (
    None
):
    current = make_state(
        ips=(
            "31.25.243.222",
            "81.90.182.109",
            "94.242.50.92",
            "213.180.193.230",
            "77.88.21.119",
        ),
        static_ips=(),
        domains=("yandex.ru", "vk.com"),
    )
    desired = make_preview(
        networks=(
            "31.25.243.222/32",
            "81.90.182.109/32",
            "94.242.50.92/32",
        ),
        domains=("yandex.ru", "vk.com"),
    )

    diff = SmartRoutingRuntimeDiffService().build(current, desired)

    assert diff.covered_ipv4_addresses == ()
    assert diff.stale_ipv4_addresses == ()
    assert diff.ipv4_replace_required is True


def test_ipv4_addresses_are_stale_when_no_direct_domains_exist() -> None:
    current = make_state(
        ips=(
            "192.0.2.10",
            "198.51.100.10",
        ),
    )
    desired = make_preview(
        networks=("192.0.2.0/24",),
    )

    diff = SmartRoutingRuntimeDiffService().build(current, desired)

    assert diff.stale_ipv4_addresses == ("198.51.100.10",)
    assert diff.ipv4_replace_required is True


def test_dns_derived_ipv4_addresses_do_not_cover_desired_static_network() -> None:
    current = make_state(
        ips=("192.0.2.10", "198.51.100.10"),
        static_ips=(),
        domains=("example.com",),
    )
    desired = make_preview(
        networks=("192.0.2.0/24",),
        domains=("example.com",),
    )

    diff = SmartRoutingRuntimeDiffService().build(current, desired)

    assert diff.current_ipv4_addresses == (
        "192.0.2.10",
        "198.51.100.10",
    )
    assert diff.covered_ipv4_addresses == ()
    assert diff.stale_ipv4_addresses == ()
    assert diff.ipv4_replace_required is True


def test_static_ipv4_addresses_are_compared_independently_from_dns_addresses() -> None:
    current = make_state(
        ips=("192.0.2.10", "198.51.100.10"),
        static_ips=("192.0.2.10",),
        domains=("example.com",),
    )
    desired = make_preview(
        networks=("192.0.2.0/24",),
        domains=("example.com",),
    )

    diff = SmartRoutingRuntimeDiffService().build(current, desired)

    assert diff.covered_ipv4_addresses == ("192.0.2.10",)
    assert diff.stale_ipv4_addresses == ()
    assert diff.ipv4_replace_required is False
