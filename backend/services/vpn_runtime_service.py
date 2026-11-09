from __future__ import annotations

from datetime import datetime, timezone

from backend.models.amneziawg_runtime_health import (
    AmneziaWGRuntimeHealth,
)
from backend.services.amneziawg_runtime_health_policy import (
    AmneziaWGRuntimeHealthPolicy,
)


class VpnRuntimeService:
    """
    Application service for VPN runtime status and lifecycle.

    When a traffic controller is configured, it is the single executor
    for LAN VPN ON/OFF operations. The controller itself performs the
    complete OpenWrt transition and verification.
    """

    def __init__(
        self,
        health_checker,
        lifecycle=None,
        traffic_controller=None,
        health_policy: AmneziaWGRuntimeHealthPolicy | None = None,
    ) -> None:
        self._health_checker = health_checker
        self._lifecycle = lifecycle
        self._traffic_controller = traffic_controller
        self._health_policy = health_policy or AmneziaWGRuntimeHealthPolicy()

    def get_health(self) -> AmneziaWGRuntimeHealth:
        health = self._health_checker.check()

        return self._health_policy.evaluate(health)

    def start(self, interface: str = "WireGuard") -> AmneziaWGRuntimeHealth:
        if self._traffic_controller is not None:
            self._traffic_controller.enable_vpn_mode()

            return self.get_health()

        if self._lifecycle is None:
            raise RuntimeError("WireGuard interface lifecycle is not configured")

        self._lifecycle.bring_up(interface)

        return self.get_health()

    def stop(self, interface: str = "WireGuard") -> AmneziaWGRuntimeHealth:
        if self._traffic_controller is not None:
            self._traffic_controller.enable_wan_mode()

            return self.get_health()

        if self._lifecycle is None:
            raise RuntimeError("WireGuard interface lifecycle is not configured")

        self._lifecycle.bring_down(interface)

        return self.get_health()

    def get_traffic_mode(self) -> str:
        if self._traffic_controller is None:
            raise RuntimeError(
                "VPN runtime traffic controller is not configured",
            )

        return self._traffic_controller.get_mode()

    @staticmethod
    def handshake_age_seconds(
        health: AmneziaWGRuntimeHealth,
    ) -> int | None:
        if health.latest_handshake is None:
            return None

        now = datetime.now(timezone.utc)
        age = now - health.latest_handshake

        if age.total_seconds() < 0:
            return 0

        return int(age.total_seconds())
