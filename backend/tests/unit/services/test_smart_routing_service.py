from unittest.mock import Mock

import pytest
from backend.infrastructure.openwrt.openwrt_traffic_routing import (
    OpenWrtTrafficRoutingResult,
    OpenWrtTrafficRoutingService,
)
from backend.infrastructure.openwrt.openwrt_traffic_routing_persistence import (
    OpenWrtTrafficRoutingPersistence,
)
from backend.models.openwrt_network_info import OpenWrtNetworkInfo
from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.models.traffic_routing_rule import (
    TrafficRoute,
    TrafficRoutingRule,
    TrafficTargetType,
)
from backend.ports.remote_command_executor import RemoteCommandExecutor
from backend.services.smart_routing_service import (
    SmartRoutingRuntimeCapabilityError,
    SmartRoutingService,
)


def make_policy() -> TrafficRoutingPolicy:
    return TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="1.1.1.1/32",
                action=TrafficRoute.DIRECT,
                priority=100,
            ),
        ]
    )


def make_domain_policy() -> TrafficRoutingPolicy:
    return TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.DOMAIN,
                target="example.com",
                action=TrafficRoute.DIRECT,
                priority=100,
            ),
        ]
    )


def make_ipv6_policy() -> TrafficRoutingPolicy:
    return TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="2001:db8::/32",
                action=TrafficRoute.DIRECT,
                priority=100,
            ),
        ]
    )


def make_ipv4_ipv6_family_policy() -> TrafficRoutingPolicy:
    return TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="1.1.1.0/24",
                action=TrafficRoute.DIRECT,
                priority=100,
                address_family="ipv6",
            ),
        ]
    )


def make_executor() -> Mock:
    executor = Mock(spec=RemoteCommandExecutor)
    executor.run.return_value = Mock(
        returncode=0,
        stdout="",
        stderr="",
    )
    return executor


def make_result(*, healthy: bool) -> OpenWrtTrafficRoutingResult:
    return OpenWrtTrafficRoutingResult(
        healthy=healthy,
        direct_ipset_exists=healthy,
        direct_rule_count=1 if healthy else 0,
        routing_table_exists=healthy,
        direct_route_exists=healthy,
        reason=None if healthy else "verification_failed",
    )


def make_network(
    *,
    lan_interface: str = "br-lan",
    wan_interface: str = "eth1",
    wan_gateway: str = "46.48.56.1",
) -> OpenWrtNetworkInfo:
    return OpenWrtNetworkInfo(
        lan_interface=lan_interface,
        lan_ipv4="192.168.8.1/24",
        wan_interface=wan_interface,
        wan_ipv4="46.48.56.64/24",
        wan_gateway=wan_gateway,
        vpn_interface="WireGuard",
        vpn_endpoint="109.172.55.99:51820",
    )


def make_service(
    *,
    runtime: Mock | None = None,
    persistence: Mock | None = None,
    network: OpenWrtNetworkInfo | None = None,
    dnsmasq: Mock | None = None,
) -> SmartRoutingService:
    executor = make_executor()

    real_runtime = OpenWrtTrafficRoutingService(
        executor=executor,
    )

    real_persistence = OpenWrtTrafficRoutingPersistence(
        executor=executor,
    )

    real_dnsmasq = Mock()

    service = SmartRoutingService(
        runtime=runtime or real_runtime,
        persistence=persistence or real_persistence,
        network=network or make_network(),
        dnsmasq=dnsmasq or real_dnsmasq,
    )

    return service


def test_apply_persists_then_verifies() -> None:
    runtime = Mock()
    runtime.ROUTING_TABLE = 200
    runtime.RULE_PRIORITY = 100
    runtime.FWMARK = 0x64
    runtime.verify.return_value = make_result(healthy=True)

    dnsmasq = Mock()
    dnsmasq.capture_snapshot.return_value = Mock()
    dnsmasq.verify.return_value = Mock(healthy=True)

    persistence = Mock()
    persistence.ROUTING_TABLE = 200
    persistence.RULE_PRIORITY = 100
    persistence.FWMARK = 0x64

    service = make_service(
        runtime=runtime,
        persistence=persistence,
        dnsmasq=dnsmasq,
    )

    result = service.apply(make_policy())

    persistence.capture_snapshot.assert_called_once_with()
    persistence.install.assert_called_once()
    runtime.verify.assert_called_once_with()
    persistence.restore_snapshot.assert_not_called()
    persistence.uninstall.assert_not_called()
    assert result.healthy is True


def test_apply_does_not_call_runtime_apply_directly() -> None:
    runtime = Mock()
    runtime.ROUTING_TABLE = 200
    runtime.RULE_PRIORITY = 100
    runtime.FWMARK = 0x64
    runtime.verify.return_value = make_result(healthy=True)

    persistence = Mock()
    persistence.ROUTING_TABLE = 200
    persistence.RULE_PRIORITY = 100
    persistence.FWMARK = 0x64

    service = make_service(
        runtime=runtime,
        persistence=persistence,
    )

    service.apply(make_policy())

    runtime.apply.assert_not_called()


def test_apply_restores_previous_state_when_persistence_fails() -> None:
    runtime = Mock()
    runtime.ROUTING_TABLE = 200
    runtime.RULE_PRIORITY = 100
    runtime.FWMARK = 0x64

    persistence = Mock()
    persistence.ROUTING_TABLE = 200
    persistence.RULE_PRIORITY = 100
    persistence.FWMARK = 0x64
    snapshot = Mock()
    persistence.capture_snapshot.return_value = snapshot
    persistence.install.side_effect = RuntimeError("install failed")

    service = make_service(
        runtime=runtime,
        persistence=persistence,
    )

    with pytest.raises(RuntimeError, match="install failed"):
        service.apply(make_policy())

    persistence.capture_snapshot.assert_called_once_with()
    runtime.verify.assert_not_called()
    persistence.restore_snapshot.assert_called_once_with(snapshot)
    persistence.uninstall.assert_not_called()


def test_apply_restores_previous_state_when_verification_fails() -> None:
    runtime = Mock()
    runtime.ROUTING_TABLE = 200
    runtime.RULE_PRIORITY = 100
    runtime.FWMARK = 0x64
    runtime.verify.return_value = make_result(healthy=False)

    persistence = Mock()
    persistence.ROUTING_TABLE = 200
    persistence.RULE_PRIORITY = 100
    persistence.FWMARK = 0x64
    snapshot = Mock()
    persistence.capture_snapshot.return_value = snapshot

    service = make_service(
        runtime=runtime,
        persistence=persistence,
    )

    with pytest.raises(
        RuntimeError,
        match="verification_failed",
    ):
        service.apply(make_policy())

    persistence.capture_snapshot.assert_called_once_with()
    persistence.install.assert_called_once()
    runtime.verify.assert_called_once_with()
    persistence.restore_snapshot.assert_called_once_with(snapshot)
    persistence.uninstall.assert_not_called()


def test_apply_rejects_awg_table_100() -> None:
    runtime = Mock()
    runtime.ROUTING_TABLE = 100
    runtime.RULE_PRIORITY = 100
    runtime.FWMARK = 0x64

    persistence = Mock()
    persistence.ROUTING_TABLE = 200
    persistence.RULE_PRIORITY = 100
    persistence.FWMARK = 0x64

    service = make_service(
        runtime=runtime,
        persistence=persistence,
    )

    with pytest.raises(
        RuntimeError,
        match="smart_routing_safety_violation",
    ):
        service.apply(make_policy())

    persistence.install.assert_not_called()


def test_apply_rejects_wrong_persistence_table() -> None:
    runtime = Mock()
    runtime.ROUTING_TABLE = 200
    runtime.RULE_PRIORITY = 100
    runtime.FWMARK = 0x64
    runtime.verify.return_value = make_result(healthy=True)

    persistence = Mock()
    persistence.ROUTING_TABLE = 100
    persistence.RULE_PRIORITY = 100
    persistence.FWMARK = 0x64

    service = make_service(
        runtime=runtime,
        persistence=persistence,
    )

    with pytest.raises(
        RuntimeError,
        match="smart_routing_safety_violation",
    ):
        service.apply(make_policy())

    persistence.install.assert_not_called()


def test_remove_only_uses_persistence() -> None:
    runtime = Mock()
    runtime.ROUTING_TABLE = 200
    runtime.RULE_PRIORITY = 100
    runtime.FWMARK = 0x64

    persistence = Mock()
    persistence.ROUTING_TABLE = 200
    persistence.RULE_PRIORITY = 100
    persistence.FWMARK = 0x64

    service = make_service(
        runtime=runtime,
        persistence=persistence,
    )

    service.remove()

    persistence.uninstall.assert_called_once()
    runtime.remove.assert_not_called()


def test_verify_delegates_to_runtime() -> None:
    runtime = Mock()
    runtime.ROUTING_TABLE = 200
    runtime.RULE_PRIORITY = 100
    runtime.FWMARK = 0x64
    expected = make_result(healthy=True)
    runtime.verify.return_value = expected

    persistence = Mock()
    persistence.ROUTING_TABLE = 200
    persistence.RULE_PRIORITY = 100
    persistence.FWMARK = 0x64

    service = make_service(
        runtime=runtime,
        persistence=persistence,
    )

    assert service.verify() is expected
    runtime.verify.assert_called_once_with()


def test_smart_routing_accepts_non_default_network_topology() -> None:
    runtime = Mock()
    runtime.ROUTING_TABLE = 200
    runtime.RULE_PRIORITY = 100
    runtime.FWMARK = 0x64
    runtime.verify.return_value = make_result(healthy=True)

    persistence = Mock()
    persistence.ROUTING_TABLE = 200
    persistence.RULE_PRIORITY = 100
    persistence.FWMARK = 0x64

    network = make_network(
        lan_interface="lan0",
        wan_interface="wan0",
        wan_gateway="10.20.30.1",
    )

    service = make_service(
        runtime=runtime,
        persistence=persistence,
        network=network,
    )

    result = service.apply(make_policy())

    assert result.healthy is True
    assert service._network.lan_interface == "lan0"
    assert service._network.wan_interface == "wan0"
    assert service._network.wan_gateway == "10.20.30.1"


def test_apply_uninstalls_when_previous_state_is_absent() -> None:
    runtime = Mock()
    runtime.ROUTING_TABLE = 200
    runtime.RULE_PRIORITY = 100
    runtime.FWMARK = 0x64
    runtime.verify.return_value = make_result(healthy=False)

    persistence = Mock()
    persistence.ROUTING_TABLE = 200
    persistence.RULE_PRIORITY = 100
    persistence.FWMARK = 0x64
    snapshot = Mock()
    snapshot.restore_script = None
    persistence.capture_snapshot.return_value = snapshot

    service = make_service(
        runtime=runtime,
        persistence=persistence,
    )

    with pytest.raises(
        RuntimeError,
        match="verification_failed",
    ):
        service.apply(make_policy())

    persistence.capture_snapshot.assert_called_once_with()
    persistence.restore_snapshot.assert_called_once_with(snapshot)


def test_apply_supports_direct_domain_runtime() -> None:
    runtime = Mock()
    runtime.ROUTING_TABLE = 200
    runtime.RULE_PRIORITY = 100
    runtime.FWMARK = 0x64
    runtime.verify.return_value = make_result(healthy=True)

    persistence = Mock()
    persistence.ROUTING_TABLE = 200
    persistence.RULE_PRIORITY = 100
    persistence.FWMARK = 0x64
    persistence.capture_snapshot.return_value = Mock()

    dnsmasq = Mock()
    dnsmasq.capture_snapshot.return_value = Mock()
    dnsmasq.verify.return_value = Mock(healthy=True)

    service = make_service(
        runtime=runtime,
        persistence=persistence,
        dnsmasq=dnsmasq,
    )

    result = service.apply(make_domain_policy())

    assert result.healthy is True
    persistence.install.assert_called_once()
    dnsmasq.apply.assert_called_once()
    dnsmasq.verify.assert_called_once_with(["example.com"])
    runtime.verify.assert_called_once_with()


def test_apply_rejects_ipv6_runtime_capability() -> None:
    runtime = Mock()
    runtime.ROUTING_TABLE = 200
    runtime.RULE_PRIORITY = 100
    runtime.FWMARK = 0x64

    persistence = Mock()
    persistence.ROUTING_TABLE = 200
    persistence.RULE_PRIORITY = 100
    persistence.FWMARK = 0x64

    service = make_service(
        runtime=runtime,
        persistence=persistence,
    )

    with pytest.raises(
        SmartRoutingRuntimeCapabilityError,
        match="IPv6 targets are not supported",
    ):
        service.apply(make_ipv6_policy())

    persistence.capture_snapshot.assert_not_called()
    persistence.install.assert_not_called()
    runtime.verify.assert_not_called()


def test_apply_rejects_ipv4_target_with_ipv6_address_family() -> None:
    runtime = Mock()
    runtime.ROUTING_TABLE = 200
    runtime.RULE_PRIORITY = 100
    runtime.FWMARK = 0x64

    persistence = Mock()
    persistence.ROUTING_TABLE = 200
    persistence.RULE_PRIORITY = 100
    persistence.FWMARK = 0x64

    service = make_service(
        runtime=runtime,
        persistence=persistence,
    )

    with pytest.raises(
        SmartRoutingRuntimeCapabilityError,
        match="address_family=ipv6",
    ):
        service.apply(make_ipv4_ipv6_family_policy())

    persistence.capture_snapshot.assert_not_called()
    persistence.install.assert_not_called()
    runtime.verify.assert_not_called()
