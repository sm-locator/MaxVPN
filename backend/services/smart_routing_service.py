from __future__ import annotations

from ipaddress import ip_network

from backend.infrastructure.openwrt.openwrt_dnsmasq_routing import (
    OpenWrtDnsmasqRoutingService,
    OpenWrtDnsmasqRoutingSnapshot,
)
from backend.infrastructure.openwrt.openwrt_traffic_routing import (
    OpenWrtTrafficRoutingResult,
    OpenWrtTrafficRoutingService,
)
from backend.infrastructure.openwrt.openwrt_traffic_routing_persistence import (
    OpenWrtTrafficRoutingPersistence,
    TrafficRoutingPersistenceSnapshot,
)
from backend.models.openwrt_network_info import OpenWrtNetworkInfo
from backend.models.traffic_routing_policy import TrafficRoutingPolicy


class SmartRoutingRuntimeCapabilityError(RuntimeError):
    """Raised when a policy cannot be applied by the current runtime."""


class SmartRoutingService:
    """
    Application-level facade for MaxVPN Smart Routing.

    MaxVPN owns only routing table 200.
    AWG routing table 100 is outside this service.
    """

    MAXVPN_ROUTING_TABLE = 200
    MAXVPN_RULE_PRIORITY = 100
    MAXVPN_FWMARK = 0x64

    def __init__(
        self,
        runtime: OpenWrtTrafficRoutingService,
        persistence: OpenWrtTrafficRoutingPersistence,
        network: OpenWrtNetworkInfo,
        dnsmasq: OpenWrtDnsmasqRoutingService,
    ) -> None:
        self._runtime = runtime
        self._persistence = persistence
        self._network = network
        self._dnsmasq = dnsmasq

    def apply(self, policy: TrafficRoutingPolicy) -> OpenWrtTrafficRoutingResult:
        self._assert_safe_configuration()
        self._assert_runtime_supported_policy(policy)

        snapshot = self._persistence.capture_snapshot()
        dnsmasq_snapshot = self._dnsmasq.capture_snapshot()

        try:
            self._persistence.install(policy)
            self._dnsmasq.apply(policy)

            result = self._runtime.verify()

            if not result.healthy:
                raise RuntimeError(
                    result.reason or "smart_routing_runtime_verification_failed"
                )

            domain_rules = [
                rule.target
                for rule in policy.rules
                if (
                    rule.enabled
                    and getattr(rule.target_type, "value", rule.target_type) == "domain"
                    and getattr(rule.action, "value", rule.action) == "direct"
                )
            ]

            dnsmasq_result = self._dnsmasq.verify(domain_rules)

            if not dnsmasq_result.healthy:
                raise RuntimeError(
                    dnsmasq_result.reason or "dnsmasq_runtime_verification_failed",
                )

            return result

        except Exception:
            self._safe_rollback(
                snapshot,
                dnsmasq_snapshot,
            )
            raise

    def remove(self) -> None:
        self._assert_safe_configuration()

        snapshot = self._persistence.capture_snapshot()

        try:
            self._persistence.uninstall()
        except Exception:
            self._safe_rollback(snapshot)
            raise

    def verify(self) -> OpenWrtTrafficRoutingResult:
        self._assert_safe_configuration()
        return self._runtime.verify()

    def _assert_safe_configuration(self) -> None:
        if not self._network.wan_interface:
            raise RuntimeError("smart_routing_safety_violation: WAN interface missing")

        if not self._network.wan_gateway:
            raise RuntimeError("smart_routing_safety_violation: WAN gateway missing")

        if not self._network.lan_interface:
            raise RuntimeError("smart_routing_safety_violation: LAN interface missing")

        if self._runtime.ROUTING_TABLE != self.MAXVPN_ROUTING_TABLE:
            raise RuntimeError(
                "smart_routing_safety_violation: "
                f"runtime table={self._runtime.ROUTING_TABLE}"
            )

        if self._runtime.RULE_PRIORITY != self.MAXVPN_RULE_PRIORITY:
            raise RuntimeError(
                "smart_routing_safety_violation: "
                f"runtime priority={self._runtime.RULE_PRIORITY}"
            )

        if self._runtime.FWMARK != self.MAXVPN_FWMARK:
            raise RuntimeError(
                "smart_routing_safety_violation: "
                f"runtime fwmark={self._runtime.FWMARK:#x}"
            )

        if self._persistence.ROUTING_TABLE != self.MAXVPN_ROUTING_TABLE:
            raise RuntimeError(
                "smart_routing_safety_violation: "
                f"persistence table={self._persistence.ROUTING_TABLE}"
            )

        if self._persistence.RULE_PRIORITY != self.MAXVPN_RULE_PRIORITY:
            raise RuntimeError(
                "smart_routing_safety_violation: "
                f"persistence priority={self._persistence.RULE_PRIORITY}"
            )

        if self._persistence.FWMARK != self.MAXVPN_FWMARK:
            raise RuntimeError(
                "smart_routing_safety_violation: "
                f"persistence fwmark={self._persistence.FWMARK:#x}"
            )

        if self.MAXVPN_ROUTING_TABLE == 100:
            raise RuntimeError(
                "smart_routing_safety_violation: MaxVPN cannot use AWG table 100"
            )

    def _assert_runtime_supported_policy(
        self,
        policy: TrafficRoutingPolicy,
    ) -> None:
        unsupported: list[str] = []

        for index, rule in enumerate(policy.rules, start=1):
            if not rule.enabled:
                continue

            target_type = getattr(rule.target_type, "value", rule.target_type)
            address_family = getattr(
                rule.address_family,
                "value",
                rule.address_family,
            )

            if target_type == "domain":
                if getattr(rule.action, "value", rule.action) != "direct":
                    unsupported.append(
                        f"rule[{index}]: only direct domain targets are supported",
                    )
                elif address_family != "any":
                    unsupported.append(
                        f"rule[{index}]: domain targets require address_family=any",
                    )
                continue

            if address_family == "ipv6":
                unsupported.append(
                    f"rule[{index}]: address_family=ipv6 is incompatible "
                    "with the current IPv4 runtime",
                )

            try:
                network = ip_network(rule.target, strict=False)
            except ValueError:
                unsupported.append(
                    f"rule[{index}]: target is not a valid IPv4 network",
                )
                continue

            if network.version != 4:
                unsupported.append(
                    f"rule[{index}]: IPv6 targets are not supported by "
                    "the current OpenWrt runtime",
                )

        if unsupported:
            raise SmartRoutingRuntimeCapabilityError(
                "smart_routing_runtime_capability_error: " + "; ".join(unsupported),
            )

    def _safe_rollback(
        self,
        snapshot: TrafficRoutingPersistenceSnapshot,
        dnsmasq_snapshot: OpenWrtDnsmasqRoutingSnapshot,
    ) -> None:
        try:
            self._persistence.restore_snapshot(snapshot)
        except Exception:
            pass

        try:
            self._dnsmasq.restore_snapshot(dnsmasq_snapshot)
        except Exception:
            # Preserve the original exception. The caller should surface
            # the failure rather than masking it with rollback failure.
            pass
