from unittest.mock import Mock, patch

from backend.application.container import (
    build_check_wireguard_health_use_case,
    build_install_maxvpn_use_case,
    build_maxvpn_final_verification_service,
    build_maxvpn_firewall_installation_service,
    build_maxvpn_monitoring_installation_service,
    build_maxvpn_preflight_service,
    build_maxvpn_rollback_service,
    build_maxvpn_wireguard_installation_service,
    build_monitor_and_recover_wireguard_use_case,
)
from backend.application.use_cases.check_wireguard_health import (
    CheckWireGuardHealthUseCase,
)
from backend.application.use_cases.install_maxvpn import (
    InstallMaxVPNUseCase,
)
from backend.application.use_cases.monitor_and_recover_wireguard import (
    MonitorAndRecoverWireGuardUseCase,
)
from backend.infrastructure.config.settings import Settings
from backend.models.maxvpn_installation import (
    InstallationPhase,
    InstallationStatus,
    InstallationStepResult,
)
from backend.services.maxvpn_firewall_installation import (
    MaxVPNFirewallInstallationService,
)
from backend.services.maxvpn_monitoring_installation import (
    MaxVPNMonitoringInstallationService,
)
from backend.services.maxvpn_preflight import MaxVPNPreflightService
from backend.services.maxvpn_rollback import MaxVPNRollbackService
from backend.services.maxvpn_wireguard_installation import (
    MaxVPNWireGuardInstallationService,
)
from backend.services.wireguard_health_policy import WireGuardHealthPolicy
from backend.services.maxvpn_final_verification import (
    MaxVPNFinalVerificationService,
)


def test_build_check_wireguard_health_use_case_uses_ssh_amneziawg_checker() -> None:
    settings = Settings(
        amneziawg_binary="awg",
        amneziawg_interface="WireGuard",
        ssh_host="192.168.8.1",
        ssh_port=22,
        ssh_username="root",
        ssh_private_key_path="~/.ssh/maxvpn_brume3",
    )

    executor = Mock()
    health_checker = Mock()

    with (
        patch(
            "backend.application.container.get_settings",
            return_value=settings,
        ),
        patch(
            "backend.application.container.SSHRemoteCommandExecutor",
            return_value=executor,
        ) as executor_class,
        patch(
            "backend.application.container.SSHAmneziaWGHealthChecker",
            return_value=health_checker,
        ) as checker_class,
    ):
        use_case = build_check_wireguard_health_use_case()

    assert isinstance(use_case, CheckWireGuardHealthUseCase)

    executor_class.assert_called_once_with(
        host="192.168.8.1",
        username="root",
        private_key_path="~/.ssh/maxvpn_brume3",
        port=22,
    )

    checker_class.assert_called_once_with(
        executor=executor,
        interface_name="WireGuard",
    )

    assert isinstance(use_case._health_policy, WireGuardHealthPolicy)
    assert use_case._health_checker is health_checker


def test_build_monitor_and_recover_wireguard_use_case() -> None:
    settings = Settings(
        amneziawg_interface="WireGuard",
        ssh_host="192.168.8.1",
        ssh_port=22,
        ssh_username="root",
        ssh_private_key_path="~/.ssh/maxvpn_brume3",
    )

    executor = Mock()

    with (
        patch(
            "backend.application.container.get_settings",
            return_value=settings,
        ),
        patch(
            "backend.application.container.SSHRemoteCommandExecutor",
            return_value=executor,
        ),
    ):
        use_case = build_monitor_and_recover_wireguard_use_case()

    assert isinstance(use_case, MonitorAndRecoverWireGuardUseCase)
    assert use_case.recovery_attempt == 0


def test_build_maxvpn_preflight_service() -> None:
    settings = Settings(
        amneziawg_interface="WireGuard",
        ssh_host="192.168.8.1",
        ssh_port=22,
        ssh_username="root",
        ssh_private_key_path="~/.ssh/maxvpn_brume3",
    )

    executor = Mock()

    with (
        patch(
            "backend.application.container.get_settings",
            return_value=settings,
        ),
        patch(
            "backend.application.container.SSHRemoteCommandExecutor",
            return_value=executor,
        ),
        patch(
            "backend.application.container.OpenWrtNetworkDiscovery",
        ) as discovery,
        patch(
            "backend.application.container.build_check_wireguard_health_use_case",
        ) as build_health,
    ):
        service = build_maxvpn_preflight_service()

    assert isinstance(service, MaxVPNPreflightService)
    discovery.assert_called_once_with(executor=executor)
    build_health.assert_not_called()
    assert service._discovery is discovery.return_value
    assert service._dynamic_health_check_factory is build_health


def test_build_maxvpn_firewall_installation_service() -> None:
    settings = Settings(
        amneziawg_interface="WireGuard",
        ssh_host="192.168.8.1",
        ssh_port=22,
        ssh_username="root",
        ssh_private_key_path="~/.ssh/maxvpn_brume3",
    )

    executor = Mock()

    with (
        patch(
            "backend.application.container.get_settings",
            return_value=settings,
        ),
        patch(
            "backend.application.container.SSHRemoteCommandExecutor",
            return_value=executor,
        ),
        patch(
            "backend.application.container.OpenWrtFirewallVerifier",
        ) as verifier,
        patch(
            "backend.application.container.OpenWrtFirewallReloadService",
        ) as reload_service,
        patch(
            "backend.application.container.OpenWrtFirewallPersistence",
        ) as persistence,
    ):
        service = build_maxvpn_firewall_installation_service()

    assert isinstance(
        service,
        MaxVPNFirewallInstallationService,
    )

    verifier.assert_called_once_with(
        executor=executor,
    )

    reload_service.assert_called_once_with(
        executor=executor,
        verifier=verifier.return_value,
    )

    persistence.assert_called_once_with(
        executor=executor,
        reload_service=reload_service.return_value,
    )


def test_build_maxvpn_wireguard_installation_service() -> None:
    health_check = Mock()

    with patch(
        "backend.application.container.build_check_wireguard_health_use_case",
        return_value=health_check,
    ):
        service = build_maxvpn_wireguard_installation_service()

    assert isinstance(
        service,
        MaxVPNWireGuardInstallationService,
    )


def test_build_maxvpn_rollback_service() -> None:
    settings = Settings(
        amneziawg_interface="WireGuard",
        ssh_host="192.168.8.1",
        ssh_port=22,
        ssh_username="root",
        ssh_private_key_path="~/.ssh/maxvpn_brume3",
    )

    executor = Mock()

    with (
        patch(
            "backend.application.container.get_settings",
            return_value=settings,
        ),
        patch(
            "backend.application.container.SSHRemoteCommandExecutor",
            return_value=executor,
        ),
        patch(
            "backend.application.container.OpenWrtFirewallVerifier",
        ) as verifier,
        patch(
            "backend.application.container.OpenWrtFirewallReloadService",
        ) as reload_service,
        patch(
            "backend.application.container.OpenWrtFirewallPersistence",
        ) as persistence,
    ):
        service = build_maxvpn_rollback_service()

    assert isinstance(
        service,
        MaxVPNRollbackService,
    )

    verifier.assert_called_once_with(
        executor=executor,
    )

    reload_service.assert_called_once_with(
        executor=executor,
        verifier=verifier.return_value,
    )

    persistence.assert_called_once_with(
        executor=executor,
        reload_service=reload_service.return_value,
    )


def test_build_maxvpn_monitoring_installation_service() -> None:
    monitor_and_recover = Mock()

    with patch(
        "backend.application.container.build_monitor_and_recover_wireguard_use_case",
        return_value=monitor_and_recover,
    ):
        service = build_maxvpn_monitoring_installation_service()

    assert isinstance(
        service,
        MaxVPNMonitoringInstallationService,
    )


def test_build_install_maxvpn_use_case() -> None:
    preflight = Mock()
    firewall = Mock()
    wireguard = Mock()
    monitoring = Mock()
    final_verification = Mock()
    rollback = Mock()

    preflight.execute.return_value = InstallationStepResult(
        phase=InstallationPhase.PREFLIGHT,
        status=InstallationStatus.SUCCESS,
    )

    firewall.execute.return_value = InstallationStepResult(
        phase=InstallationPhase.FIREWALL,
        status=InstallationStatus.SUCCESS,
    )

    wireguard.execute.return_value = InstallationStepResult(
        phase=InstallationPhase.WIREGUARD,
        status=InstallationStatus.SUCCESS,
    )

    monitoring.execute.return_value = InstallationStepResult(
        phase=InstallationPhase.MONITORING,
        status=InstallationStatus.SUCCESS,
    )

    final_verification.execute.return_value = InstallationStepResult(
        phase=InstallationPhase.FINAL_VERIFY,
        status=InstallationStatus.SUCCESS,
    )

    rollback.execute.return_value = InstallationStepResult(
        phase=InstallationPhase.ROLLBACK,
        status=InstallationStatus.SUCCESS,
    )

    with (
        patch(
            "backend.application.container.build_maxvpn_preflight_service",
            return_value=preflight,
        ),
        patch(
            "backend.application.container.build_maxvpn_firewall_installation_service",
            return_value=firewall,
        ),
        patch(
            "backend.application.container.build_maxvpn_wireguard_installation_service",
            return_value=wireguard,
        ),
        patch(
            "backend.application.container.build_maxvpn_monitoring_installation_service",
            return_value=monitoring,
        ),
        patch(
            "backend.application.container.build_maxvpn_final_verification_service",
            return_value=final_verification,
        ),
        patch(
            "backend.application.container.build_maxvpn_rollback_service",
            return_value=rollback,
        ),
    ):
        use_case = build_install_maxvpn_use_case()

    assert isinstance(use_case, InstallMaxVPNUseCase)

    result = use_case.execute()

    assert result.status == InstallationStatus.SUCCESS
    assert result.completed_phase == InstallationPhase.COMPLETE
    assert result.reason is None

    preflight.execute.assert_called_once_with()
    firewall.execute.assert_called_once_with()
    wireguard.execute.assert_called_once_with()
    monitoring.execute.assert_called_once_with()
    final_verification.execute.assert_called_once_with()
    rollback.execute.assert_not_called()

    assert result.steps[-1].phase == InstallationPhase.FINAL_VERIFY
    assert result.steps[-1].status == InstallationStatus.SUCCESS


def test_build_maxvpn_final_verification_service() -> None:
    settings = Settings(
        amneziawg_interface="WireGuard",
        ssh_host="192.168.8.1",
        ssh_port=22,
        ssh_username="root",
        ssh_private_key_path="~/.ssh/maxvpn_brume3",
    )

    executor = Mock()

    with (
        patch(
            "backend.application.container.get_settings",
            return_value=settings,
        ),
        patch(
            "backend.application.container.SSHRemoteCommandExecutor",
            return_value=executor,
        ),
        patch(
            "backend.application.container.OpenWrtFirewallVerifier",
        ) as verifier,
        patch(
            "backend.application.container.build_check_wireguard_health_use_case",
        ) as health_check,
    ):
        service = build_maxvpn_final_verification_service()

    assert isinstance(
        service,
        MaxVPNFinalVerificationService,
    )

    verifier.assert_called_once_with(
        executor=executor,
    )

    health_check.assert_called_once_with()
