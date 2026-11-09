from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from backend.infrastructure.wireguard.config_backed_amneziawg_runtime_health import (
    ConfigBackedAmneziaWGRuntimeHealth,
)


def test_config_read_is_deferred_until_health_check() -> None:
    executor = Mock()
    config_source = Mock()
    config_source.read.side_effect = RuntimeError(
        "uci_get_failed: network.WireGuard.private_key"
    )

    checker = ConfigBackedAmneziaWGRuntimeHealth(
        executor=executor,
        interface_name="WireGuard",
        config_source=config_source,
    )

    config_source.read.assert_not_called()

    checker.check()

    config_source.read.assert_called_once()


def test_missing_uci_config_returns_unhealthy_result_not_exception() -> None:
    executor = Mock()
    executor.run.return_value = SimpleNamespace(
        returncode=0,
        stdout="WireGuard: <POINTOPOINT,NOARP,UP,LOWER_UP> mtu 1420 qdisc noqueue",
        stderr="",
    )
    config_source = Mock()
    config_source.read.side_effect = RuntimeError(
        "uci_get_failed: network.WireGuard.private_key"
    )

    result = ConfigBackedAmneziaWGRuntimeHealth(
        executor=executor,
        interface_name="WireGuard",
        config_source=config_source,
    ).check()

    assert result.healthy is False
    assert result.reason == "awg_config_unavailable"
    assert result.interface_exists is True
    assert result.interface_up is True
    assert result.expected_peer_found is False
    assert result.endpoint_route_ok is False
