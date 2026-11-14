from datetime import datetime, timezone
from unittest.mock import Mock

from backend.models.amneziawg_config import (
    AmneziaWGConfig,
    AmneziaWGInterface,
    AmneziaWGPeer,
)
from backend.models.amneziawg_runtime_health import (
    AmneziaWGRuntimeHealth,
)
from backend.services.amneziawg_runtime_apply_verifier import (
    AmneziaWGRuntimeApplyVerifier,
)
from backend.services.amneziawg_runtime_applier import (
    AmneziaWGRuntimeApplyResult,
    AmneziaWGRuntimePlan,
)


def make_config() -> AmneziaWGConfig:
    return AmneziaWGConfig(
        interface=AmneziaWGInterface(
            private_key="private-key",
            address="10.9.9.200/32",
            mtu=1380,
            jc=5,
        ),
        peer=AmneziaWGPeer(
            public_key="server-public-key",
            allowed_ips=("0.0.0.0/0",),
            endpoint="194.26.192.36:39743",
            persistent_keepalive=25,
            preshared_key="psk",
        ),
    )


def make_plan() -> AmneziaWGRuntimePlan:
    return AmneziaWGRuntimePlan(
        interface="WireGuard",
        runtime_path="/tmp/maxvpn-awg-runtime.conf",
        runtime_config="[Interface]\nPrivateKey = private-key\n",
        upload_command=("sh", "-c", "upload"),
        sync_command=(
            "awg",
            "syncconf",
            "WireGuard",
            "/tmp/maxvpn-awg-runtime.conf",
        ),
    )


def make_apply_result(
    *,
    applied: bool,
    reason: str | None = None,
) -> AmneziaWGRuntimeApplyResult:
    return AmneziaWGRuntimeApplyResult(
        plan=make_plan(),
        upload_returncode=0 if applied else 1,
        sync_returncode=0 if applied else None,
        uploaded=applied,
        applied=applied,
        reason=reason,
    )


def make_health(
    *,
    healthy: bool,
    reason: str | None = None,
) -> AmneziaWGRuntimeHealth:
    return AmneziaWGRuntimeHealth(
        interface_exists=True,
        interface_up=True,
        expected_peer_found=True,
        expected_endpoint=True,
        listen_port=43095,
        latest_handshake=datetime.now(timezone.utc),
        rx_bytes=1000,
        tx_bytes=1000,
        endpoint_route_ok=True,
        healthy=healthy,
        reason=reason,
        checked_at=datetime.now(timezone.utc),
    )


def test_execute_applies_waits_and_verifies():
    applier = Mock()
    applier.apply.return_value = make_apply_result(
        applied=True,
    )

    health_checker = Mock()
    health_checker.check.return_value = make_health(
        healthy=True,
    )

    sleeper = Mock()

    service = AmneziaWGRuntimeApplyVerifier(
        applier=applier,
        health_checker=health_checker,
        wait_seconds=15,
        sleeper=sleeper,
    )

    result = service.execute(make_config())

    assert result.verified is True
    assert result.reason is None
    assert result.health is not None
    assert result.health.healthy is True

    applier.apply.assert_called_once_with(
        config=make_config(),
        interface="WireGuard",
        runtime_path="/tmp/maxvpn-awg-runtime.conf",
    )

    sleeper.assert_called_once_with(15)
    health_checker.check.assert_called_once_with()


def test_execute_does_not_verify_when_apply_fails():
    applier = Mock()
    applier.apply.return_value = make_apply_result(
        applied=False,
        reason="awg_syncconf_failed",
    )

    health_checker = Mock()
    sleeper = Mock()

    service = AmneziaWGRuntimeApplyVerifier(
        applier=applier,
        health_checker=health_checker,
        wait_seconds=15,
        sleeper=sleeper,
    )

    result = service.execute(make_config())

    assert result.verified is False
    assert result.health is None
    assert result.reason == "awg_syncconf_failed"

    sleeper.assert_not_called()
    health_checker.check.assert_not_called()


def test_execute_reports_failed_health_without_recovery():
    applier = Mock()
    applier.apply.return_value = make_apply_result(
        applied=True,
    )

    health_checker = Mock()
    health_checker.check.return_value = make_health(
        healthy=False,
        reason="no_handshake",
    )

    sleeper = Mock()

    service = AmneziaWGRuntimeApplyVerifier(
        applier=applier,
        health_checker=health_checker,
        wait_seconds=15,
        sleeper=sleeper,
    )

    result = service.execute(make_config())

    assert result.verified is False
    assert result.health is not None
    assert result.health.reason == "no_handshake"
    assert result.reason == "no_handshake"

    sleeper.assert_called_once_with(15)
    health_checker.check.assert_called_once_with()

    # No recovery executor exists here by design.


def test_zero_wait_skips_sleep():
    applier = Mock()
    applier.apply.return_value = make_apply_result(
        applied=True,
    )

    health_checker = Mock()
    health_checker.check.return_value = make_health(
        healthy=True,
    )

    sleeper = Mock()

    service = AmneziaWGRuntimeApplyVerifier(
        applier=applier,
        health_checker=health_checker,
        wait_seconds=0,
        sleeper=sleeper,
    )

    result = service.execute(make_config())

    assert result.verified is True
    sleeper.assert_not_called()


def test_negative_wait_is_rejected():
    applier = Mock()
    health_checker = Mock()

    try:
        AmneziaWGRuntimeApplyVerifier(
            applier=applier,
            health_checker=health_checker,
            wait_seconds=-1,
        )
    except ValueError as exc:
        assert str(exc) == "wait_seconds must not be negative"
    else:
        raise AssertionError("ValueError was not raised")
