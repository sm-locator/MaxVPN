from backend.models.wireguard_recovery import (
    WireGuardRecoveryAction,
    WireGuardRecoveryPlan,
)
from backend.ports.wireguard_recovery_executor import (
    WireGuardRecoveryExecutor,
)


class StubWireGuardRecoveryExecutor(WireGuardRecoveryExecutor):
    def __init__(self) -> None:
        self.executed_plan: WireGuardRecoveryPlan | None = None

    def execute(self, plan: WireGuardRecoveryPlan) -> None:
        self.executed_plan = plan


def test_recovery_executor_accepts_recovery_plan() -> None:
    plan = WireGuardRecoveryPlan(
        action=WireGuardRecoveryAction.RESTART_INTERFACE,
        attempt=1,
        max_attempts=3,
        backoff_seconds=5,
        reason="handshake_timeout",
    )

    executor = StubWireGuardRecoveryExecutor()

    executor.execute(plan)

    assert executor.executed_plan == plan
