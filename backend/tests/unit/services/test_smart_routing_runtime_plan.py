from unittest.mock import Mock

from backend.services.smart_routing_runtime_diff import (
    SmartRoutingRuntimeDiffService,
)
from backend.services.smart_routing_runtime_plan import (
    SmartRoutingRuntimePlanService,
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


def test_build_combines_current_desired_and_diff() -> None:
    collector = Mock()
    preview_service = Mock()
    diff_service = Mock()

    current = make_state(
        ips=("192.0.2.10", "198.51.100.10"),
    )

    desired = make_preview(
        networks=("192.0.2.0/24",),
    )

    diff = SmartRoutingRuntimeDiffService().build(current, desired)

    collector.collect.return_value = current
    preview_service.build.return_value = desired
    diff_service.build.return_value = diff

    policy = Mock()

    plan = SmartRoutingRuntimePlanService(
        state_collector=collector,
        preview_service=preview_service,
        diff_service=diff_service,
    ).build(policy)

    assert plan.current == current
    assert plan.desired == desired
    assert plan.diff == diff
    assert plan.has_changes is True

    collector.collect.assert_called_once()
    preview_service.build.assert_called_once_with(policy)
    diff_service.build.assert_called_once_with(current, desired)


def test_render_shows_read_only_plan() -> None:
    collector = Mock()
    preview_service = Mock()
    diff_service = Mock()

    current = make_state(
        ips=("192.0.2.10", "198.51.100.10"),
    )

    desired = make_preview(
        networks=("192.0.2.0/24",),
    )

    diff = SmartRoutingRuntimeDiffService().build(current, desired)

    collector.collect.return_value = current
    preview_service.build.return_value = desired
    diff_service.build.return_value = diff

    plan = SmartRoutingRuntimePlanService(
        state_collector=collector,
        preview_service=preview_service,
        diff_service=diff_service,
    ).build(Mock())

    rendered = plan.render()

    assert "SMART ROUTING RUNTIME DIFF" in rendered
    assert "192.0.2.0/24" in rendered
    assert "198.51.100.10" in rendered
    assert "REPLACE MAXVPN_DIRECT" in rendered
    assert "RESULT: CHANGES REQUIRED" in rendered


def test_render_reports_no_changes() -> None:
    collector = Mock()
    preview_service = Mock()
    diff_service = Mock()

    current = make_state(
        ips=("192.0.2.10",),
        domains=("example.com",),
    )

    desired = make_preview(
        networks=("192.0.2.0/24",),
        domains=("example.com",),
    )

    diff = SmartRoutingRuntimeDiffService().build(current, desired)

    collector.collect.return_value = current
    preview_service.build.return_value = desired
    diff_service.build.return_value = diff

    plan = SmartRoutingRuntimePlanService(
        state_collector=collector,
        preview_service=preview_service,
        diff_service=diff_service,
    ).build(Mock())

    rendered = plan.render()

    assert "action:             NO CHANGE" in rendered
    assert "RESULT: NO CHANGES" in rendered
