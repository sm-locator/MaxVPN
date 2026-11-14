from pathlib import Path
from unittest.mock import Mock

from backend.application.context.maxvpn_installation_context import (
    MaxVPNInstallationContext,
)
from backend.models.maxvpn_installation import (
    InstallationPhase,
    InstallationStatus,
)
from backend.models.openwrt_network_info import OpenWrtNetworkInfo
from backend.ports.remote_command_executor import RemoteCommandExecutor
from backend.services.maxvpn_preflight import MaxVPNPreflightService


def make_health(
    *,
    interface_exists: bool = True,
    interface_up: bool = True,
) -> Mock:
    health = Mock()
    health.interface_exists = interface_exists
    health.interface_up = interface_up
    return health


def make_executor() -> Mock:
    executor = Mock(spec=RemoteCommandExecutor)
    executor.run.return_value = Mock(
        returncode=0,
        stdout="",
        stderr="",
    )
    return executor


def make_network() -> OpenWrtNetworkInfo:
    return OpenWrtNetworkInfo(
        lan_interface="br-lan",
        lan_ipv4="192.168.8.1/24",
        wan_interface="eth1",
        wan_ipv4="46.48.56.64/24",
        wan_gateway="46.48.56.1",
        vpn_interface="WireGuard",
        vpn_endpoint="109.172.55.99:51820",
    )


def make_service(
    *,
    executor: Mock | None = None,
    health_check: Mock | None = None,
    private_key_path: str = "/tmp/maxvpn_brume3",
    discovery: Mock | None = None,
    context: MaxVPNInstallationContext | None = None,
    dynamic_health_check_factory: Mock | None = None,
) -> MaxVPNPreflightService:
    health_check = health_check or Mock(
        execute=Mock(
            return_value=make_health(),
        )
    )

    return MaxVPNPreflightService(
        executor=executor or make_executor(),
        private_key_path=private_key_path,
        discovery=discovery
        or Mock(
            discover=Mock(
                return_value=make_network(),
            )
        ),
        context=context or MaxVPNInstallationContext(),
        dynamic_health_check_factory=dynamic_health_check_factory
        or Mock(
            return_value=health_check,
        ),
    )


def test_preflight_succeeds_when_all_checks_pass(
    tmp_path: Path,
) -> None:
    private_key = tmp_path / "maxvpn_brume3"
    private_key.write_text("test-key")

    executor = make_executor()
    health_check = Mock(
        execute=Mock(
            return_value=make_health(),
        )
    )
    discovery = Mock(
        discover=Mock(
            return_value=make_network(),
        )
    )
    context = MaxVPNInstallationContext()

    service = make_service(
        executor=executor,
        health_check=health_check,
        discovery=discovery,
        context=context,
        private_key_path=str(private_key),
    )

    result = service.execute()

    assert result.phase == InstallationPhase.PREFLIGHT
    assert result.status == InstallationStatus.SUCCESS
    assert result.reason is None
    assert context.network == make_network()

    discovery.discover.assert_called_once_with()
    health_check.execute.assert_called_once_with()


def test_preflight_fails_when_private_key_is_missing(
    tmp_path: Path,
) -> None:
    executor = make_executor()

    service = make_service(
        executor=executor,
        private_key_path=str(tmp_path / "missing-key"),
    )

    result = service.execute()

    assert result.status == InstallationStatus.FAILED
    assert result.reason == "ssh_private_key_not_found"


def test_preflight_fails_when_ssh_connectivity_fails(
    tmp_path: Path,
) -> None:
    private_key = tmp_path / "maxvpn_brume3"
    private_key.write_text("test-key")

    executor = make_executor()
    executor.run.side_effect = [
        Mock(returncode=1, stdout="", stderr="ssh failed"),
    ]

    service = make_service(
        executor=executor,
        private_key_path=str(private_key),
    )

    result = service.execute()

    assert result.status == InstallationStatus.FAILED
    assert result.reason == "ssh_connectivity_failed"


def test_preflight_fails_when_firewall_user_is_missing(
    tmp_path: Path,
) -> None:
    private_key = tmp_path / "maxvpn_brume3"
    private_key.write_text("test-key")

    executor = make_executor()
    executor.run.side_effect = [
        Mock(returncode=0, stdout="", stderr=""),
        Mock(
            returncode=1,
            stdout="",
            stderr="missing",
        ),
    ]

    service = make_service(
        executor=executor,
        private_key_path=str(private_key),
    )

    result = service.execute()

    assert result.status == InstallationStatus.FAILED
    assert result.reason == "firewall_user_missing"


def test_preflight_fails_when_wireguard_interface_is_missing(
    tmp_path: Path,
) -> None:
    private_key = tmp_path / "maxvpn_brume3"
    private_key.write_text("test-key")

    executor = make_executor()
    executor.run.side_effect = [
        Mock(returncode=0, stdout="", stderr=""),
        Mock(returncode=0, stdout="", stderr=""),
        Mock(
            returncode=1,
            stdout="",
            stderr="missing",
        ),
    ]

    service = make_service(
        executor=executor,
        private_key_path=str(private_key),
    )

    result = service.execute()

    assert result.status == InstallationStatus.FAILED
    assert result.reason == "wireguard_interface_missing"


def test_preflight_fails_when_wireguard_is_down(
    tmp_path: Path,
) -> None:
    private_key = tmp_path / "maxvpn_brume3"
    private_key.write_text("test-key")

    executor = make_executor()

    health_check = Mock(
        execute=Mock(
            return_value=make_health(
                interface_exists=True,
                interface_up=False,
            )
        )
    )

    service = make_service(
        executor=executor,
        health_check=health_check,
        private_key_path=str(private_key),
    )

    executor.run.side_effect = [
        Mock(returncode=0, stdout="", stderr=""),
        Mock(returncode=0, stdout="", stderr=""),
        Mock(returncode=0, stdout="", stderr=""),
    ]

    result = service.execute()

    assert result.status == InstallationStatus.FAILED
    assert result.reason == "wireguard_interface_down"


def test_preflight_fails_when_health_check_raises(
    tmp_path: Path,
) -> None:
    private_key = tmp_path / "maxvpn_brume3"
    private_key.write_text("test-key")

    executor = make_executor()

    health_check = Mock(execute=Mock(side_effect=RuntimeError("health check failed")))

    service = make_service(
        executor=executor,
        health_check=health_check,
        private_key_path=str(private_key),
    )

    executor.run.side_effect = [
        Mock(returncode=0, stdout="", stderr=""),
        Mock(returncode=0, stdout="", stderr=""),
        Mock(returncode=0, stdout="", stderr=""),
    ]

    result = service.execute()

    assert result.status == InstallationStatus.FAILED
    assert result.reason == "wireguard_health_check_failed"


def test_preflight_accepts_degraded_wireguard_status_when_interface_is_up(
    tmp_path: Path,
) -> None:
    private_key = tmp_path / "maxvpn_brume3"
    private_key.write_text("test-key")

    executor = make_executor()

    health = make_health(
        interface_exists=True,
        interface_up=True,
    )
    health.status.value = "degraded"

    health_check = Mock(
        execute=Mock(
            return_value=health,
        )
    )

    service = make_service(
        executor=executor,
        health_check=health_check,
        private_key_path=str(private_key),
    )

    executor.run.side_effect = [
        Mock(returncode=0, stdout="", stderr=""),
        Mock(returncode=0, stdout="", stderr=""),
        Mock(returncode=0, stdout="", stderr=""),
    ]

    result = service.execute()

    assert result.status == InstallationStatus.SUCCESS


def test_preflight_stores_discovered_network(
    tmp_path: Path,
) -> None:
    private_key = tmp_path / "maxvpn_brume3"
    private_key.write_text("test-key")

    network = OpenWrtNetworkInfo(
        lan_interface="br-lan",
        lan_ipv4="192.168.8.1/24",
        wan_interface="eth1",
        wan_ipv4="46.48.56.64/24",
        wan_gateway="46.48.56.1",
        vpn_interface="WireGuard",
        vpn_endpoint="109.172.55.99:51820",
    )

    discovery = Mock()
    discovery.discover.return_value = network

    context = MaxVPNInstallationContext()

    service = make_service(
        private_key_path=str(private_key),
        discovery=discovery,
        context=context,
    )

    result = service.execute()

    assert result.status == InstallationStatus.SUCCESS
    assert context.network == network
    discovery.discover.assert_called_once_with()


def test_preflight_fails_when_network_discovery_fails(
    tmp_path: Path,
) -> None:
    private_key = tmp_path / "maxvpn_brume3"
    private_key.write_text("test-key")

    discovery = Mock()
    discovery.discover.side_effect = RuntimeError("discovery failed")

    context = MaxVPNInstallationContext()

    service = make_service(
        private_key_path=str(private_key),
        discovery=discovery,
        context=context,
    )

    result = service.execute()

    assert result.status == InstallationStatus.FAILED
    assert result.reason == "network_discovery_failed"
    assert context.network is None
    discovery.discover.assert_called_once_with()


def test_preflight_uses_discovered_vpn_interface(
    tmp_path: Path,
) -> None:
    private_key = tmp_path / "maxvpn_brume3"
    private_key.write_text("test-key")

    network = OpenWrtNetworkInfo(
        lan_interface="br-lan",
        lan_ipv4="192.168.8.1/24",
        wan_interface="eth1",
        wan_ipv4="46.48.56.64/24",
        wan_gateway="46.48.56.1",
        vpn_interface="CustomAWG",
        vpn_endpoint="109.172.55.99:51820",
    )

    discovery = Mock()
    discovery.discover.return_value = network

    health_check = Mock()
    health_check.execute.return_value = make_health()

    health_factory = Mock(
        return_value=health_check,
    )

    executor = make_executor()

    service = make_service(
        executor=executor,
        discovery=discovery,
        context=MaxVPNInstallationContext(),
        health_check=health_check,
        dynamic_health_check_factory=health_factory,
        private_key_path=str(private_key),
    )

    result = service.execute()

    assert result.status == InstallationStatus.SUCCESS

    commands = [call.args[0] for call in executor.run.call_args_list]

    assert [
        "ip",
        "link",
        "show",
        "dev",
        "CustomAWG",
    ] in commands

    health_factory.assert_called_once_with("CustomAWG")
