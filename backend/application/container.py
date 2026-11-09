from __future__ import annotations

from functools import lru_cache

from backend.application.context.maxvpn_installation_context import (
    MaxVPNInstallationContext,
)
from backend.application.use_cases.add_russian_direct_preset import (
    AddRussianDirectPresetUseCase,
)
from backend.application.use_cases.apply_smart_routing import (
    ApplySmartRoutingUseCase,
)
from backend.application.use_cases.check_wireguard_health import (
    CheckWireGuardHealthUseCase,
)
from backend.application.use_cases.create_client import CreateClientUseCase
from backend.application.use_cases.export_existing_client_config import (
    ExportExistingClientConfigUseCase,
)
from backend.application.use_cases.install_maxvpn import InstallMaxVPNUseCase
from backend.application.use_cases.monitor_and_recover_wireguard import (
    MonitorAndRecoverWireGuardUseCase,
)
from backend.application.use_cases.monitor_wireguard import (
    MonitorWireGuardUseCase,
)
from backend.application.use_cases.preview_smart_routing_runtime import (
    PreviewSmartRoutingRuntimeUseCase,
)
from backend.application.use_cases.recover_wireguard import (
    RecoverWireGuardUseCase,
)
from backend.application.use_cases.register_client import RegisterClientUseCase
from backend.application.use_cases.select_best_server import (
    SelectBestServerUseCase,
)
from backend.application.use_cases.server.initialize_wireguard_server import (
    InitializeWireGuardServerUseCase,
)
from backend.infrastructure.config.settings import get_settings
from backend.infrastructure.database.dry_run_unit_of_work import (
    DryRunUnitOfWork,
)
from backend.infrastructure.database.factory import (
    create_client_repository,
    create_server_repository,
    create_session,
)
from backend.infrastructure.database.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from backend.infrastructure.openwrt.openwrt_amneziawg_config_persistence import (
    OpenWrtAmneziaWGConfigPersistence,
)
from backend.infrastructure.openwrt.openwrt_amneziawg_config_source import (
    OpenWrtAmneziaWGConfigSource,
)
from backend.infrastructure.openwrt.openwrt_amneziawg_runtime_profile_source import (
    OpenWrtAmneziaWGRuntimeProfileSource,
)
from backend.infrastructure.openwrt.openwrt_dnsmasq_routing import (
    OpenWrtDnsmasqRoutingService,
)
from backend.infrastructure.openwrt.openwrt_firewall_persistence import (
    OpenWrtFirewallPersistence,
)
from backend.infrastructure.openwrt.openwrt_firewall_verifier import (
    OpenWrtFirewallVerifier,
)
from backend.infrastructure.openwrt.openwrt_network_discovery import (
    OpenWrtNetworkDiscovery,
)
from backend.infrastructure.openwrt.openwrt_smart_routing_dns_cleanup import (
    OpenWrtSmartRoutingDnsCleanup,
)
from backend.infrastructure.openwrt.openwrt_traffic_routing import (
    OpenWrtTrafficRoutingService,
)
from backend.infrastructure.openwrt.openwrt_traffic_routing_persistence import (
    OpenWrtTrafficRoutingPersistence,
)
from backend.infrastructure.openwrt.openwrt_vpn_runtime_traffic_controller import (
    OpenWrtVpnRuntimeTrafficController,
)
from backend.infrastructure.ssh.ssh_remote_command_executor import (
    SSHRemoteCommandExecutor,
)
from backend.infrastructure.wireguard.dry_run_peer_manager import (
    DryRunWireGuardPeerManager,
)
from backend.infrastructure.wireguard.ssh_amneziawg_health_checker import (
    SSHAmneziaWGHealthChecker,
)
from backend.infrastructure.wireguard.ssh_amneziawg_runtime_config_source import (
    SSHAmneziaWGRuntimeConfigSource,
)
from backend.infrastructure.wireguard.ssh_amneziawg_runtime_health import (
    ExpectedAmneziaWGPeer,
    SSHAmneziaWGRuntimeHealth,
)
from backend.infrastructure.wireguard.ssh_amneziawg_runtime_snapshot import (
    SSHAmneziaWGRuntimeSnapshot,
)
from backend.infrastructure.wireguard.ssh_wireguard_interface_lifecycle import (
    SSHWireGuardInterfaceLifecycle,
)
from backend.infrastructure.wireguard.ssh_wireguard_recovery_executor import (
    SSHWireGuardRecoveryExecutor,
)
from backend.infrastructure.wireguard.system_peer_manager import (
    SystemWireGuardPeerManager,
)
from backend.infrastructure.wireguard.system_server_key_store import (
    SystemWireGuardServerKeyStore,
)
from backend.infrastructure.wireguard.system_server_manager import (
    SystemWireGuardServerManager,
)
from backend.models.amneziawg_config import AmneziaWGConfig
from backend.models.maxvpn_installation import (
    InstallationPhase,
)
from backend.models.openwrt_network_info import OpenWrtNetworkInfo
from backend.models.vpn_traffic_policy import VpnTrafficPolicy
from backend.policy.registry import PolicyRegistry
from backend.services.amneziawg_runtime_applier import (
    AmneziaWGRuntimeApplier,
)
from backend.services.amneziawg_runtime_manager import (
    AmneziaWGRuntimeManager,
)
from backend.services.database_address_allocator import DatabaseAddressAllocator
from backend.services.maxvpn_final_verification import (
    MaxVPNFinalVerificationService,
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
from backend.services.openwrt_firewall_reload import OpenWrtFirewallReloadService
from backend.services.routing_service import RoutingService
from backend.services.server_selector import ServerSelector
from backend.services.smart_routing_dependency_diagnostic_service import (
    SmartRoutingDependencyDiagnosticService,
)
from backend.services.smart_routing_dependency_diagnostic_session import (
    SmartRoutingDependencyDiagnosticSessionService,
)
from backend.services.smart_routing_dns_background_worker import (
    SmartRoutingDnsBackgroundWorker,
)
from backend.services.smart_routing_dns_domain_state import (
    SmartRoutingDnsDomainStateStore,
)
from backend.services.smart_routing_dns_ipset_reconciler import (
    SmartRoutingDnsIpSetReconciler,
)
from backend.services.smart_routing_dns_log_reader import (
    SmartRoutingDnsLogReader,
)
from backend.services.smart_routing_dns_reconciliation_coordinator import (
    SmartRoutingDnsReconciliationCoordinator,
)
from backend.services.smart_routing_dns_response_observer import (
    SmartRoutingDnsResponseObserver,
)
from backend.services.smart_routing_domain_diagnostic import (
    SmartRoutingDomainDiagnosticService,
)
from backend.services.smart_routing_policy_service import (
    SmartRoutingPolicyService,
)
from backend.services.smart_routing_runtime_plan import (
    SmartRoutingRuntimePlanService,
)
from backend.services.smart_routing_runtime_state import (
    SmartRoutingRuntimeStateCollector,
)
from backend.services.smart_routing_service import SmartRoutingService
from backend.services.vpn_config_cipher import VPNConfigCipher
from backend.services.vpn_profile_service import VpnProfileService
from backend.services.vpn_runtime_service import VpnRuntimeService
from backend.services.wireguard_cli_key_provider import WireGuardCLIKeyProvider
from backend.services.wireguard_config_renderer import WireGuardConfigRenderer
from backend.services.wireguard_health_policy import WireGuardHealthPolicy
from backend.services.wireguard_monitor import WireGuardMonitor
from backend.services.wireguard_recovery_policy import WireGuardRecoveryPolicy
from sqlalchemy.orm import Session

from app.repositories.vpn_profile import VpnProfileRepository


def build_create_client_use_case() -> CreateClientUseCase:
    session = create_session()

    server_repository = create_server_repository(session)
    client_repository = create_client_repository(session)

    routing = RoutingService(
        repository=server_repository,
        selector=ServerSelector(),
        engine=PolicyRegistry.create_default(),
    )

    select_server = SelectBestServerUseCase(routing)

    return CreateClientUseCase(
        select_server=select_server,
        key_provider=WireGuardCLIKeyProvider(),
        address_allocator=DatabaseAddressAllocator(
            client_repository=client_repository,
        ),
    )


def build_register_client_use_case(
    dry_run: bool = False,
) -> RegisterClientUseCase:
    session = create_session()

    if dry_run:
        unit_of_work = DryRunUnitOfWork(session)
        peer_manager = DryRunWireGuardPeerManager()
    else:
        unit_of_work = SqlAlchemyUnitOfWork(session)

        settings = get_settings()

        peer_manager = SystemWireGuardPeerManager(
            interface_name=settings.wireguard_interface,
            binary=settings.wireguard_binary,
        )

    return RegisterClientUseCase(
        unit_of_work=unit_of_work,
        peer_manager=peer_manager,
    )


def build_initialize_wireguard_server_use_case(
    dry_run: bool = False,
) -> InitializeWireGuardServerUseCase:
    settings = get_settings()

    if dry_run:
        raise NotImplementedError("WireGuard server dry-run is not implemented yet.")

    session = create_session()
    unit_of_work = SqlAlchemyUnitOfWork(session)

    server_manager = SystemWireGuardServerManager(
        interface_name=settings.wireguard_interface,
        wg_binary=settings.wireguard_binary,
        backend="userspace",
    )

    peer_manager = SystemWireGuardPeerManager(
        interface_name=settings.wireguard_interface,
        binary=settings.wireguard_binary,
    )

    server_key_store = SystemWireGuardServerKeyStore()

    return InitializeWireGuardServerUseCase(
        server_manager=server_manager,
        server_key_store=server_key_store,
        peer_manager=peer_manager,
        unit_of_work=unit_of_work,
        settings=settings,
    )


def build_export_existing_client_config_use_case():
    session = create_session()
    unit_of_work = SqlAlchemyUnitOfWork(session)

    return ExportExistingClientConfigUseCase(
        unit_of_work=unit_of_work,
        renderer=WireGuardConfigRenderer(),
    )


def build_check_wireguard_health_use_case(
    interface_name: str | None = None,
) -> CheckWireGuardHealthUseCase:
    settings = get_settings()

    executor = SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
    )

    health_checker = SSHAmneziaWGHealthChecker(
        executor=executor,
        interface_name=interface_name or settings.amneziawg_interface,
    )

    health_policy = WireGuardHealthPolicy()

    return CheckWireGuardHealthUseCase(
        health_checker=health_checker,
        health_policy=health_policy,
    )


def build_monitor_and_recover_wireguard_use_case() -> MonitorAndRecoverWireGuardUseCase:
    settings = get_settings()

    executor = SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
    )

    health_checker = SSHAmneziaWGHealthChecker(
        executor=executor,
        interface_name=settings.amneziawg_interface,
    )

    health_check = CheckWireGuardHealthUseCase(
        health_checker=health_checker,
        health_policy=WireGuardHealthPolicy(),
    )

    monitor = MonitorWireGuardUseCase(
        health_check=health_check,
        monitor=WireGuardMonitor(),
    )

    recovery_executor = SSHWireGuardRecoveryExecutor(
        executor=executor,
        interface_name=settings.amneziawg_interface,
    )

    recovery = RecoverWireGuardUseCase(
        recovery_executor=recovery_executor,
        health_check=health_check,
    )

    recovery_policy = WireGuardRecoveryPolicy()

    return MonitorAndRecoverWireGuardUseCase(
        monitor=monitor,
        recovery_policy=recovery_policy,
        recovery=recovery,
    )


def build_apply_smart_routing_use_case() -> ApplySmartRoutingUseCase:
    session = create_session()

    return ApplySmartRoutingUseCase(
        smart_routing=build_smart_routing_service_from_discovery(),
        policy_service=SmartRoutingPolicyService(session),
    )


def build_smart_routing_service_from_discovery() -> SmartRoutingService:
    settings = get_settings()

    executor = SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
    )

    network = OpenWrtNetworkDiscovery(
        executor=executor,
    ).discover()

    return build_smart_routing_service(network)


def build_smart_routing_domain_diagnostic_service() -> (
    SmartRoutingDomainDiagnosticService
):
    settings = get_settings()

    executor = SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
    )

    return SmartRoutingDomainDiagnosticService(
        executor=executor,
    )


@lru_cache(maxsize=1)
def build_smart_routing_dependency_diagnostic_session_service() -> (
    SmartRoutingDependencyDiagnosticSessionService
):
    settings = get_settings()

    executor = SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
    )

    reader = SmartRoutingDnsLogReader(
        executor=executor,
    )

    analyzer = SmartRoutingDependencyDiagnosticService()

    return SmartRoutingDependencyDiagnosticSessionService(
        reader=reader,
        analyzer=analyzer,
    )


def build_smart_routing_dns_coordinator(
    executor: SSHRemoteCommandExecutor,
    *,
    state_repository=None,
) -> SmartRoutingDnsReconciliationCoordinator:
    log_reader = SmartRoutingDnsLogReader(
        executor=executor,
    )

    response_observer = SmartRoutingDnsResponseObserver()

    state_store = SmartRoutingDnsDomainStateStore()

    ipset_reconciler = SmartRoutingDnsIpSetReconciler()

    runtime_state = SmartRoutingRuntimeStateCollector(
        executor=executor,
    )

    cleanup = OpenWrtSmartRoutingDnsCleanup(
        executor=executor,
    )

    return SmartRoutingDnsReconciliationCoordinator(
        log_reader=log_reader,
        response_observer=response_observer,
        state_store=state_store,
        ipset_reconciler=ipset_reconciler,
        runtime_state=runtime_state,
        cleanup=cleanup,
        state_repository=state_repository,
    )


def build_smart_routing_dns_background_worker() -> SmartRoutingDnsBackgroundWorker:
    settings = get_settings()

    executor = SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
        timeout=15.0,
    )

    runtime_state = SmartRoutingRuntimeStateCollector(
        executor=executor,
    )

    from app.database.session import SessionLocal
    from app.repositories.smart_routing_dns_state import (
        SmartRoutingDnsStateRepository,
    )

    state_repository = SmartRoutingDnsStateRepository(SessionLocal)
    coordinator = build_smart_routing_dns_coordinator(
        executor,
        state_repository=state_repository,
    )

    return SmartRoutingDnsBackgroundWorker(
        coordinator=coordinator,
        runtime_state=runtime_state,
        interval_seconds=2.0,
        persistent_state_enabled=True,
    )


def build_add_russian_direct_preset_use_case(
    db: Session,
) -> AddRussianDirectPresetUseCase:
    return AddRussianDirectPresetUseCase(db)


def build_preview_smart_routing_runtime_use_case(
    db: Session,
) -> PreviewSmartRoutingRuntimeUseCase:
    settings = get_settings()

    executor = SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
    )

    state_collector = SmartRoutingRuntimeStateCollector(
        executor=executor,
    )

    plan_service = SmartRoutingRuntimePlanService(
        state_collector=state_collector,
    )

    return PreviewSmartRoutingRuntimeUseCase(
        plan_service=plan_service,
        policy_service=SmartRoutingPolicyService(db),
    )


def build_smart_routing_service(
    network: OpenWrtNetworkInfo,
) -> SmartRoutingService:
    settings = get_settings()

    executor = SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
    )

    runtime = OpenWrtTrafficRoutingService(
        executor=executor,
        lan_interface=network.lan_interface,
        wan_interface=network.wan_interface,
        wan_gateway=network.wan_gateway,
    )

    persistence = OpenWrtTrafficRoutingPersistence(
        executor=executor,
        lan_interface=network.lan_interface,
        wan_interface=network.wan_interface,
        wan_gateway=network.wan_gateway,
    )

    dnsmasq = OpenWrtDnsmasqRoutingService(
        executor=executor,
    )

    return SmartRoutingService(
        runtime=runtime,
        persistence=persistence,
        network=network,
        dnsmasq=dnsmasq,
    )


def build_maxvpn_preflight_service(
    context: MaxVPNInstallationContext | None = None,
) -> MaxVPNPreflightService:
    settings = get_settings()

    context = context or MaxVPNInstallationContext()

    executor = SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
    )

    discovery = OpenWrtNetworkDiscovery(
        executor=executor,
    )

    return MaxVPNPreflightService(
        executor=executor,
        private_key_path=settings.ssh_private_key_path,
        discovery=discovery,
        context=context,
        dynamic_health_check_factory=build_check_wireguard_health_use_case,
    )


def build_maxvpn_firewall_installation_service() -> MaxVPNFirewallInstallationService:
    settings = get_settings()

    executor = SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
    )

    reload_verifier = OpenWrtFirewallVerifier(
        executor=executor,
    )

    reload_service = OpenWrtFirewallReloadService(
        executor=executor,
        verifier=reload_verifier,
    )

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
        reload_service=reload_service,
    )

    policy = VpnTrafficPolicy(
        lan_interface="br-lan",
        vpn_interface=settings.amneziawg_interface,
        wan_interface="eth1",
        allow_lan_to_vpn=True,
        allow_lan_to_wan=False,
        allow_lan_to_wan_ipv6=False,
        allow_vpn_endpoint_via_wan=True,
    )

    return MaxVPNFirewallInstallationService(
        persistence=persistence,
        policy=policy,
    )


def build_maxvpn_wireguard_installation_service() -> MaxVPNWireGuardInstallationService:
    health_check = build_check_wireguard_health_use_case()

    return MaxVPNWireGuardInstallationService(
        health_check=health_check,
    )


def build_maxvpn_rollback_service() -> MaxVPNRollbackService:
    settings = get_settings()

    executor = SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
    )

    reload_verifier = OpenWrtFirewallVerifier(
        executor=executor,
    )

    reload_service = OpenWrtFirewallReloadService(
        executor=executor,
        verifier=reload_verifier,
    )

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
        reload_service=reload_service,
    )

    return MaxVPNRollbackService(
        persistence=persistence,
    )


def build_maxvpn_monitoring_installation_service() -> (
    MaxVPNMonitoringInstallationService
):
    monitor_and_recover = build_monitor_and_recover_wireguard_use_case()

    return MaxVPNMonitoringInstallationService(
        monitor_and_recover=monitor_and_recover,
    )


def build_install_maxvpn_use_case() -> InstallMaxVPNUseCase:
    context = MaxVPNInstallationContext()

    preflight = build_maxvpn_preflight_service(
        context=context,
    )
    firewall = build_maxvpn_firewall_installation_service()
    wireguard = build_maxvpn_wireguard_installation_service()
    monitoring = build_maxvpn_monitoring_installation_service()
    final_verification = build_maxvpn_final_verification_service()
    rollback = build_maxvpn_rollback_service()

    return InstallMaxVPNUseCase(
        actions={
            InstallationPhase.PREFLIGHT: preflight.execute,
            InstallationPhase.FIREWALL: firewall.execute,
            InstallationPhase.WIREGUARD: wireguard.execute,
            InstallationPhase.MONITORING: monitoring.execute,
            InstallationPhase.FINAL_VERIFY: final_verification.execute,
        },
        rollback=rollback.execute,
    )


def build_maxvpn_final_verification_service() -> MaxVPNFinalVerificationService:
    settings = get_settings()

    executor = SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
    )

    firewall_verifier = OpenWrtFirewallVerifier(
        executor=executor,
    )

    wireguard_health_check = build_check_wireguard_health_use_case()

    return MaxVPNFinalVerificationService(
        firewall_verifier=firewall_verifier,
        wireguard_health_check=wireguard_health_check,
    )


def build_amneziawg_runtime_health(
    interface: str = "WireGuard",
):
    settings = get_settings()

    executor = SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
    )

    config_source = OpenWrtAmneziaWGConfigSource(
        executor=executor,
        interface=interface,
    )

    from backend.infrastructure.wireguard import config_backed_amneziawg_runtime_health

    # Defer router UCI reads until check(). A missing/incomplete config must
    # become an unhealthy runtime result, not a dependency-construction 500.
    return config_backed_amneziawg_runtime_health.ConfigBackedAmneziaWGRuntimeHealth(
        executor=executor,
        interface_name=interface,
        config_source=config_source,
    )


def build_amneziawg_runtime_manager(
    config: AmneziaWGConfig,
) -> AmneziaWGRuntimeManager:
    settings = get_settings()

    executor = SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
    )

    expected_peer = ExpectedAmneziaWGPeer(
        public_key=config.peer.public_key,
        endpoint=config.peer.endpoint,
    )

    health_checker = SSHAmneziaWGRuntimeHealth(
        executor=executor,
        interface_name=settings.amneziawg_interface,
        expected_peer=expected_peer,
    )

    applier = AmneziaWGRuntimeApplier(
        command_executor=executor,
    )

    snapshot = SSHAmneziaWGRuntimeSnapshot(
        executor=executor,
    )

    lifecycle = SSHWireGuardInterfaceLifecycle(
        executor=executor,
    )

    return AmneziaWGRuntimeManager(
        applier=applier,
        snapshot=snapshot,
        health_checker=health_checker,
        lifecycle=lifecycle,
    )


def build_vpn_runtime_service() -> VpnRuntimeService:
    settings = get_settings()

    executor = SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
    )

    return VpnRuntimeService(
        health_checker=build_amneziawg_runtime_health(
            settings.amneziawg_interface,
        ),
        lifecycle=SSHWireGuardInterfaceLifecycle(
            executor=executor,
        ),
        traffic_controller=OpenWrtVpnRuntimeTrafficController(
            executor=executor,
        ),
    )


def build_vpn_profile_service(
    session,
) -> VpnProfileService:
    settings = get_settings()

    encryption_key = settings.vpn_config_encryption_key

    if not encryption_key:
        raise RuntimeError("VPN_CONFIG_ENCRYPTION_KEY is not configured")

    executor = SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
    )

    config_source = OpenWrtAmneziaWGConfigSource(
        executor=executor,
        interface=settings.amneziawg_interface,
    )

    runtime_profile_source = OpenWrtAmneziaWGRuntimeProfileSource(
        executor=executor,
    )

    runtime_config_source = SSHAmneziaWGRuntimeConfigSource(
        executor=executor,
    )

    persistent_config_writer = OpenWrtAmneziaWGConfigPersistence(
        executor=executor,
    )

    return VpnProfileService(
        repository=VpnProfileRepository(session),
        cipher=VPNConfigCipher(encryption_key),
        runtime_manager_factory=build_amneziawg_runtime_manager,
        config_source=config_source,
        runtime_profile_source=runtime_profile_source,
        runtime_config_source=runtime_config_source,
        persistent_config_writer=persistent_config_writer,
    )


def build_vless_profile_service(session):
    """Build the encrypted VLESS profile persistence service."""
    from backend.services.vless_profile_importer import VlessProfileImporter
    from backend.services.vless_profile_service import VlessProfileService

    from app.repositories.vless_profile import VlessProfileRepository
    from app.repositories.vless_runtime_settings import VlessRuntimeSettingsRepository

    settings = get_settings()
    encryption_key = settings.vpn_config_encryption_key
    if not encryption_key:
        raise RuntimeError("VPN_CONFIG_ENCRYPTION_KEY is not configured")

    return VlessProfileService(
        repository=VlessProfileRepository(session),
        cipher=VPNConfigCipher(encryption_key),
        importer=VlessProfileImporter(),
        settings_repository=VlessRuntimeSettingsRepository(session),
    )


def build_vless_runtime_service(session):
    """Build the VLESS runtime service without changing LAN routing."""
    from backend.infrastructure.openwrt.openwrt_vless_singbox_controller import (
        OpenWrtVlessSingBoxController,
    )
    from backend.infrastructure.openwrt.openwrt_vpn_runtime_traffic_controller import (
        OpenWrtVpnRuntimeTrafficController,
    )
    from backend.services.vless_runtime_service import VlessRuntimeService

    settings = get_settings()
    executor = SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
    )

    # VLESS needs the persistent firewall/hotplug support files, but must not
    # run the legacy WireGuard verifier or trigger a global fw3 reload here.
    vless_firewall_persistence = OpenWrtFirewallPersistence(executor=executor)
    vless_firewall_policy = VpnTrafficPolicy(
        lan_interface="br-lan",
        vpn_interface=settings.amneziawg_interface,
        wan_interface="eth1",
        allow_lan_to_vpn=True,
        allow_lan_to_wan=False,
        allow_lan_to_wan_ipv6=False,
        allow_vpn_endpoint_via_wan=True,
    )
    traffic_controller = OpenWrtVpnRuntimeTrafficController(
        executor,
        firewall_installer=(
            lambda: vless_firewall_persistence.install_vless_runtime_support(
                vless_firewall_policy
            )
        ),
        firewall_watchdog_starter=vless_firewall_persistence.start_vless_watchdog,
    )

    return VlessRuntimeService(
        profile_service=build_vless_profile_service(session),
        controller=OpenWrtVlessSingBoxController(executor),
        traffic_controller=traffic_controller,
    )
