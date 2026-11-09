from unittest.mock import Mock, patch

from backend.application.container import (
    build_apply_smart_routing_use_case,
    build_smart_routing_service,
    build_smart_routing_service_from_discovery,
)
from backend.application.use_cases.apply_smart_routing import (
    ApplySmartRoutingUseCase,
)
from backend.infrastructure.openwrt.openwrt_network_discovery import (
    OpenWrtNetworkDiscovery,
)
from backend.models.openwrt_network_info import OpenWrtNetworkInfo
from backend.services.smart_routing_policy_service import (
    SmartRoutingPolicyService,
)
from backend.services.smart_routing_service import SmartRoutingService


def make_network() -> OpenWrtNetworkInfo:
    return OpenWrtNetworkInfo(
        lan_interface="lan0",
        lan_ipv4="10.0.0.1/24",
        wan_interface="wan0",
        wan_ipv4="10.20.30.64/24",
        wan_gateway="10.20.30.1",
        vpn_interface="CustomAWG",
        vpn_endpoint="203.0.113.10:51820",
    )


def test_build_smart_routing_service_uses_discovered_network() -> None:
    network = make_network()

    with (
        patch(
            "backend.application.container.get_settings",
        ) as get_settings,
        patch(
            "backend.application.container.SSHRemoteCommandExecutor",
        ) as executor_factory,
    ):
        settings = Mock()
        settings.ssh_host = "192.168.8.1"
        settings.ssh_username = "root"
        settings.ssh_private_key_path = "~/.ssh/maxvpn_brume3"
        settings.ssh_port = 22
        get_settings.return_value = settings

        executor = Mock()
        executor_factory.return_value = executor

        service = build_smart_routing_service(network)

    assert isinstance(service, SmartRoutingService)
    assert service._network is network

    assert service._runtime._lan_interface == "lan0"
    assert service._runtime._wan_interface == "wan0"
    assert service._runtime._wan_gateway == "10.20.30.1"

    assert service._persistence._lan_interface == "lan0"
    assert service._persistence._wan_interface == "wan0"
    assert service._persistence._wan_gateway == "10.20.30.1"


def test_build_smart_routing_service_from_discovery_discovers_network() -> None:
    network = make_network()

    with (
        patch(
            "backend.application.container.get_settings",
        ) as get_settings,
        patch(
            "backend.application.container.SSHRemoteCommandExecutor",
        ) as executor_factory,
        patch(
            "backend.application.container.create_session",
        ) as create_session,
        patch.object(
            OpenWrtNetworkDiscovery,
            "discover",
            return_value=network,
        ) as discover,
    ):
        settings = Mock()
        settings.ssh_host = "192.168.8.1"
        settings.ssh_username = "root"
        settings.ssh_private_key_path = "~/.ssh/maxvpn_brume3"
        settings.ssh_port = 22
        get_settings.return_value = settings

        executor = Mock()
        executor_factory.return_value = executor

        session = Mock()
        create_session.return_value = session

        service = build_smart_routing_service_from_discovery()

    assert isinstance(service, SmartRoutingService)
    assert service._network is network

    create_session.assert_not_called()
    discover.assert_called_once_with()


def test_build_apply_smart_routing_use_case_creates_policy_service() -> None:
    network = make_network()

    with (
        patch(
            "backend.application.container.get_settings",
        ) as get_settings,
        patch(
            "backend.application.container.SSHRemoteCommandExecutor",
        ) as executor_factory,
        patch(
            "backend.application.container.create_session",
        ) as create_session,
        patch(
            "backend.application.container.OpenWrtNetworkDiscovery.discover",
            return_value=network,
        ),
    ):
        settings = Mock()
        settings.ssh_host = "192.168.8.1"
        settings.ssh_username = "root"
        settings.ssh_private_key_path = "~/.ssh/maxvpn_brume3"
        settings.ssh_port = 22
        get_settings.return_value = settings

        executor = Mock()
        executor_factory.return_value = executor

        session = Mock()
        create_session.return_value = session

        use_case = build_apply_smart_routing_use_case()

    assert isinstance(use_case, ApplySmartRoutingUseCase)
    assert isinstance(use_case._smart_routing, SmartRoutingService)
    assert use_case._smart_routing._network is network
    assert isinstance(
        use_case._policy_service,
        SmartRoutingPolicyService,
    )
    assert use_case._policy_service.repository.db is session
    create_session.assert_called_once_with()
