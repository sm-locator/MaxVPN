from unittest.mock import Mock

from backend.application.use_cases.install_maxvpn import (
    InstallMaxVPNUseCase,
)
from backend.models.maxvpn_installation import (
    InstallationPhase,
    InstallationStatus,
    InstallationStepResult,
)


def step(
    phase: InstallationPhase,
    status: InstallationStatus,
    reason: str | None = None,
) -> InstallationStepResult:
    return InstallationStepResult(
        phase=phase,
        status=status,
        reason=reason,
    )


def test_install_completes_all_phases_successfully() -> None:
    actions = {
        phase: Mock(
            return_value=step(
                phase,
                InstallationStatus.SUCCESS,
            )
        )
        for phase in InstallMaxVPNUseCase.PHASES
    }

    rollback = Mock()

    use_case = InstallMaxVPNUseCase(
        actions=actions,
        rollback=rollback,
    )

    result = use_case.execute()

    assert result.status == InstallationStatus.SUCCESS
    assert result.completed_phase == InstallationPhase.COMPLETE
    assert result.successful is True
    assert result.reason is None

    assert len(result.steps) == 5
    rollback.assert_not_called()

    for phase in InstallMaxVPNUseCase.PHASES:
        actions[phase].assert_called_once_with()


def test_install_stops_on_failure_and_rolls_back() -> None:
    actions = {
        phase: Mock(
            return_value=step(
                phase,
                InstallationStatus.SUCCESS,
            )
        )
        for phase in InstallMaxVPNUseCase.PHASES
    }

    actions[InstallationPhase.WIREGUARD].return_value = step(
        InstallationPhase.WIREGUARD,
        InstallationStatus.FAILED,
        "wireguard_unavailable",
    )

    rollback = Mock(
        return_value=step(
            InstallationPhase.ROLLBACK,
            InstallationStatus.SUCCESS,
        )
    )

    use_case = InstallMaxVPNUseCase(
        actions=actions,
        rollback=rollback,
    )

    result = use_case.execute()

    assert result.status == InstallationStatus.FAILED
    assert result.completed_phase == InstallationPhase.ROLLBACK
    assert result.successful is False
    assert result.reason == "wireguard_unavailable"

    rollback.assert_called_once_with()

    actions[InstallationPhase.PREFLIGHT].assert_called_once_with()
    actions[InstallationPhase.FIREWALL].assert_called_once_with()
    actions[InstallationPhase.WIREGUARD].assert_called_once_with()

    actions[InstallationPhase.MONITORING].assert_not_called()
    actions[InstallationPhase.FINAL_VERIFY].assert_not_called()

    assert len(result.steps) == 4


def test_install_stops_on_degraded_phase() -> None:
    actions = {
        phase: Mock(
            return_value=step(
                phase,
                InstallationStatus.SUCCESS,
            )
        )
        for phase in InstallMaxVPNUseCase.PHASES
    }

    actions[InstallationPhase.FIREWALL].return_value = step(
        InstallationPhase.FIREWALL,
        InstallationStatus.DEGRADED,
        "fw3_nonzero_but_maxvpn_healthy",
    )

    rollback = Mock()

    use_case = InstallMaxVPNUseCase(
        actions=actions,
        rollback=rollback,
    )

    result = use_case.execute()

    assert result.status == InstallationStatus.DEGRADED
    assert result.completed_phase == InstallationPhase.FIREWALL
    assert result.successful is True
    assert result.reason == "fw3_nonzero_but_maxvpn_healthy"

    rollback.assert_not_called()

    actions[InstallationPhase.PREFLIGHT].assert_called_once_with()
    actions[InstallationPhase.FIREWALL].assert_called_once_with()

    actions[InstallationPhase.WIREGUARD].assert_not_called()
    actions[InstallationPhase.MONITORING].assert_not_called()
    actions[InstallationPhase.FINAL_VERIFY].assert_not_called()


def test_install_preserves_step_results_in_order() -> None:
    actions = {
        phase: Mock(
            return_value=step(
                phase,
                InstallationStatus.SUCCESS,
            )
        )
        for phase in InstallMaxVPNUseCase.PHASES
    }

    rollback = Mock()

    use_case = InstallMaxVPNUseCase(
        actions=actions,
        rollback=rollback,
    )

    result = use_case.execute()

    assert [item.phase for item in result.steps] == [
        InstallationPhase.PREFLIGHT,
        InstallationPhase.FIREWALL,
        InstallationPhase.WIREGUARD,
        InstallationPhase.MONITORING,
        InstallationPhase.FINAL_VERIFY,
    ]


def test_install_preserves_primary_failure_when_rollback_fails() -> None:
    actions = {
        phase: Mock(
            return_value=step(
                phase,
                InstallationStatus.SUCCESS,
            )
        )
        for phase in InstallMaxVPNUseCase.PHASES
    }

    actions[InstallationPhase.FINAL_VERIFY].return_value = step(
        InstallationPhase.FINAL_VERIFY,
        InstallationStatus.FAILED,
        "final_verification_failed",
    )

    rollback = Mock(
        return_value=step(
            InstallationPhase.ROLLBACK,
            InstallationStatus.FAILED,
            "rollback_failed",
        )
    )

    use_case = InstallMaxVPNUseCase(
        actions=actions,
        rollback=rollback,
    )

    result = use_case.execute()

    assert result.status == InstallationStatus.FAILED
    assert result.completed_phase == InstallationPhase.ROLLBACK
    assert result.reason == "final_verification_failed"
    assert result.steps[-1].reason == "rollback_failed"


def test_install_stops_immediately_when_preflight_fails() -> None:
    preflight = Mock(
        return_value=step(
            InstallationPhase.PREFLIGHT,
            InstallationStatus.FAILED,
            "ssh_connectivity_failed",
        )
    )

    firewall = Mock()
    wireguard = Mock()
    monitoring = Mock()
    final_verify = Mock()

    rollback = Mock(
        return_value=step(
            InstallationPhase.ROLLBACK,
            InstallationStatus.SUCCESS,
        )
    )

    actions = {
        InstallationPhase.PREFLIGHT: preflight,
        InstallationPhase.FIREWALL: firewall,
        InstallationPhase.WIREGUARD: wireguard,
        InstallationPhase.MONITORING: monitoring,
        InstallationPhase.FINAL_VERIFY: final_verify,
    }

    use_case = InstallMaxVPNUseCase(
        actions=actions,
        rollback=rollback,
    )

    result = use_case.execute()

    assert result.status == InstallationStatus.FAILED
    assert result.completed_phase == InstallationPhase.ROLLBACK
    assert result.reason == "ssh_connectivity_failed"

    preflight.assert_called_once_with()
    firewall.assert_not_called()
    wireguard.assert_not_called()
    monitoring.assert_not_called()
    final_verify.assert_not_called()
    rollback.assert_called_once_with()

    assert [item.phase for item in result.steps] == [
        InstallationPhase.PREFLIGHT,
        InstallationPhase.ROLLBACK,
    ]


def test_install_proceeds_to_firewall_after_successful_preflight() -> None:
    preflight = Mock(
        return_value=step(
            InstallationPhase.PREFLIGHT,
            InstallationStatus.SUCCESS,
        )
    )

    firewall = Mock(
        return_value=step(
            InstallationPhase.FIREWALL,
            InstallationStatus.SUCCESS,
        )
    )

    wireguard = Mock(
        return_value=step(
            InstallationPhase.WIREGUARD,
            InstallationStatus.SUCCESS,
        )
    )

    monitoring = Mock(
        return_value=step(
            InstallationPhase.MONITORING,
            InstallationStatus.SUCCESS,
        )
    )

    final_verify = Mock(
        return_value=step(
            InstallationPhase.FINAL_VERIFY,
            InstallationStatus.SUCCESS,
        )
    )

    rollback = Mock()

    actions = {
        InstallationPhase.PREFLIGHT: preflight,
        InstallationPhase.FIREWALL: firewall,
        InstallationPhase.WIREGUARD: wireguard,
        InstallationPhase.MONITORING: monitoring,
        InstallationPhase.FINAL_VERIFY: final_verify,
    }

    use_case = InstallMaxVPNUseCase(
        actions=actions,
        rollback=rollback,
    )

    result = use_case.execute()

    assert result.status == InstallationStatus.SUCCESS
    assert result.completed_phase == InstallationPhase.COMPLETE

    preflight.assert_called_once_with()
    firewall.assert_called_once_with()
    wireguard.assert_called_once_with()
    monitoring.assert_called_once_with()
    final_verify.assert_called_once_with()
    rollback.assert_not_called()
