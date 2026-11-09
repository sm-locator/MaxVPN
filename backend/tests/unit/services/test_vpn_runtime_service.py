from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from backend.models.amneziawg_runtime_health import AmneziaWGRuntimeHealth
from backend.services.vpn_runtime_service import VpnRuntimeService


def make_health(healthy: bool) -> AmneziaWGRuntimeHealth:
    now = datetime.now(timezone.utc)

    return AmneziaWGRuntimeHealth(
        interface_exists=healthy,
        interface_up=healthy,
        expected_peer_found=healthy,
        expected_endpoint=healthy,
        listen_port=51874 if healthy else None,
        latest_handshake=now - timedelta(seconds=10) if healthy else None,
        rx_bytes=1000 if healthy else 0,
        tx_bytes=1000 if healthy else 0,
        endpoint_route_ok=healthy,
        healthy=healthy,
        reason=None if healthy else "handshake_timeout",
        checked_at=now,
    )


def make_service(
    *,
    health: AmneziaWGRuntimeHealth,
):
    checker = Mock()
    checker.check.return_value = health

    lifecycle = Mock()
    traffic = Mock()

    service = VpnRuntimeService(
        health_checker=checker,
        lifecycle=lifecycle,
        traffic_controller=traffic,
    )

    return service, checker, lifecycle, traffic


def test_start_uses_traffic_controller_without_lifecycle() -> None:
    service, checker, lifecycle, traffic = make_service(
        health=make_health(True),
    )

    result = service.start()

    traffic.enable_vpn_mode.assert_called_once_with()
    lifecycle.bring_up.assert_not_called()
    checker.check.assert_called_once_with()

    assert result.healthy is True


def test_stop_uses_traffic_controller_without_lifecycle() -> None:
    service, checker, lifecycle, traffic = make_service(
        health=make_health(False),
    )

    result = service.stop()

    traffic.enable_wan_mode.assert_called_once_with()
    lifecycle.bring_down.assert_not_called()
    checker.check.assert_called_once_with()

    assert result.healthy is False


def test_start_falls_back_to_lifecycle_when_controller_is_missing() -> None:
    checker = Mock()
    checker.check.return_value = make_health(True)

    lifecycle = Mock()

    service = VpnRuntimeService(
        health_checker=checker,
        lifecycle=lifecycle,
        traffic_controller=None,
    )

    result = service.start()

    lifecycle.bring_up.assert_called_once_with("WireGuard")
    checker.check.assert_called_once_with()

    assert result.healthy is True


def test_stop_falls_back_to_lifecycle_when_controller_is_missing() -> None:
    checker = Mock()
    checker.check.return_value = make_health(False)

    lifecycle = Mock()

    service = VpnRuntimeService(
        health_checker=checker,
        lifecycle=lifecycle,
        traffic_controller=None,
    )

    result = service.stop()

    lifecycle.bring_down.assert_called_once_with("WireGuard")
    checker.check.assert_called_once_with()

    assert result.healthy is False


def test_start_requires_lifecycle_when_no_controller() -> None:
    checker = Mock()

    service = VpnRuntimeService(
        health_checker=checker,
        lifecycle=None,
        traffic_controller=None,
    )

    with pytest.raises(
        RuntimeError,
        match="WireGuard interface lifecycle is not configured",
    ):
        service.start()


def test_stop_requires_lifecycle_when_no_controller() -> None:
    checker = Mock()

    service = VpnRuntimeService(
        health_checker=checker,
        lifecycle=None,
        traffic_controller=None,
    )

    with pytest.raises(
        RuntimeError,
        match="WireGuard interface lifecycle is not configured",
    ):
        service.stop()


def test_get_traffic_mode_uses_traffic_controller() -> None:
    service, checker, lifecycle, traffic = make_service(
        health=make_health(True),
    )

    traffic.get_mode.return_value = "vpn"

    result = service.get_traffic_mode()

    traffic.get_mode.assert_called_once_with()
    checker.check.assert_not_called()

    assert result == "vpn"


def test_get_traffic_mode_returns_wan_from_traffic_controller() -> None:
    service, checker, lifecycle, traffic = make_service(
        health=make_health(False),
    )

    traffic.get_mode.return_value = "wan"

    result = service.get_traffic_mode()

    traffic.get_mode.assert_called_once_with()
    checker.check.assert_not_called()

    assert result == "wan"
