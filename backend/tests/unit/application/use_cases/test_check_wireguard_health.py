from datetime import datetime, timezone

from backend.application.use_cases.check_wireguard_health import (
    CheckWireGuardHealthUseCase,
)
from backend.models.wireguard_health import (
    WireGuardHealth,
    WireGuardHealthStatus,
)
from backend.ports.wireguard_health_checker import WireGuardHealthChecker
from backend.services.wireguard_health_policy import WireGuardHealthPolicy


class StubWireGuardHealthChecker(WireGuardHealthChecker):
    def __init__(self, health: WireGuardHealth) -> None:
        self._health = health
        self.check_calls = 0

    def check(self) -> WireGuardHealth:
        self.check_calls += 1
        return self._health


def make_health() -> WireGuardHealth:
    checked_at = datetime.now(timezone.utc)

    return WireGuardHealth(
        interface_exists=True,
        interface_up=True,
        listen_port=45121,
        peer_count=1,
        latest_handshake=checked_at,
        rx_bytes=100,
        tx_bytes=200,
        status=WireGuardHealthStatus.UNKNOWN,
        reason=None,
        checked_at=checked_at,
    )


def test_execute_checks_and_evaluates_wireguard_health() -> None:
    health = make_health()
    checker = StubWireGuardHealthChecker(health)

    policy = WireGuardHealthPolicy(
        now_provider=lambda: health.checked_at,
    )

    use_case = CheckWireGuardHealthUseCase(
        health_checker=checker,
        health_policy=policy,
    )

    result = use_case.execute()

    assert checker.check_calls == 1
    assert result is not health
    assert result.interface_exists is True
    assert result.interface_up is True
    assert result.listen_port == 45121
    assert result.peer_count == 1
    assert result.rx_bytes == 100
    assert result.tx_bytes == 200
    assert result.status is WireGuardHealthStatus.HEALTHY
    assert result.reason is None


def test_execute_returns_failed_state_from_policy() -> None:
    checked_at = datetime.now(timezone.utc)

    health = WireGuardHealth(
        interface_exists=False,
        interface_up=False,
        listen_port=None,
        peer_count=0,
        latest_handshake=None,
        rx_bytes=0,
        tx_bytes=0,
        status=WireGuardHealthStatus.UNKNOWN,
        reason=None,
        checked_at=checked_at,
    )

    checker = StubWireGuardHealthChecker(health)

    policy = WireGuardHealthPolicy(
        now_provider=lambda: checked_at,
    )

    use_case = CheckWireGuardHealthUseCase(
        health_checker=checker,
        health_policy=policy,
    )

    result = use_case.execute()

    assert result.status is WireGuardHealthStatus.FAILED
    assert result.reason == "interface_not_found"
