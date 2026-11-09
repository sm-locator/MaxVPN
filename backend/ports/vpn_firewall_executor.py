from __future__ import annotations

from abc import ABC, abstractmethod

from backend.models.vpn_traffic_policy import VpnTrafficPolicy


class VpnFirewallExecutor(ABC):
    """
    Port for applying VPN fail-closed firewall policy.
    """

    @abstractmethod
    def build_commands(
        self,
        policy: VpnTrafficPolicy,
    ) -> list[list[str]]:
        """
        Build firewall commands without executing them.
        """
        raise NotImplementedError

    @abstractmethod
    def apply(
        self,
        policy: VpnTrafficPolicy,
    ) -> None:
        """
        Apply firewall policy.
        """
        raise NotImplementedError
