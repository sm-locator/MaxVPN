from __future__ import annotations

from .engine import PolicyEngine
from .rules.devices import DevicePolicy
from .rules.geo import GeoPolicy
from .rules.load import LoadPolicy
from .rules.server import ServerPolicy
from .rules.subscription import SubscriptionPolicy


class PolicyRegistry:
    """
    Factory for creating PolicyEngine instances.

    Defines the order of policy execution.
    """

    @staticmethod
    def create_default() -> PolicyEngine:
        """
        Default policy pipeline.
        """

        return PolicyEngine(
            [
                SubscriptionPolicy(),
                DevicePolicy(),
                ServerPolicy(),
                LoadPolicy(),
                GeoPolicy(),
            ]
        )
