from __future__ import annotations

from abc import ABC, abstractmethod

from backend.models.wireguard_recovery import WireGuardRecoveryPlan


class WireGuardRecoveryExecutor(ABC):
    """
    Port for executing a WireGuard recovery plan.
    """

    @abstractmethod
    def execute(self, plan: WireGuardRecoveryPlan) -> None:
        """
        Execute the recovery plan.
        """
        raise NotImplementedError
