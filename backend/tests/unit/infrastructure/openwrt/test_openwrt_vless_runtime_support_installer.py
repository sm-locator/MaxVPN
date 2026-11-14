from unittest.mock import Mock

from backend.infrastructure.openwrt.openwrt_firewall_persistence import (
    OpenWrtFirewallPersistence,
)
from backend.models.vpn_traffic_policy import VpnTrafficPolicy
from backend.ports.remote_command_executor import RemoteCommandExecutor
from backend.services.openwrt_firewall_reload import OpenWrtFirewallReloadService


def _policy() -> VpnTrafficPolicy:
    return VpnTrafficPolicy(
        lan_interface="br-lan",
        vpn_interface="WireGuard",
        wan_interface="eth1",
        allow_lan_to_vpn=True,
        allow_lan_to_wan=False,
        allow_lan_to_wan_ipv6=False,
        allow_vpn_endpoint_via_wan=True,
    )


def test_vless_runtime_support_installs_files_without_fw3_reload_or_verifier() -> None:
    executor = Mock(spec=RemoteCommandExecutor)
    executor.run.return_value = Mock(returncode=0, stdout="", stderr="")
    reload_service = Mock(spec=OpenWrtFirewallReloadService)
    persistence = OpenWrtFirewallPersistence(
        executor=executor,
        reload_service=reload_service,
    )

    persistence.install_vless_runtime_support(_policy())

    commands = [call.args[0] for call in executor.run.call_args_list]
    flattened = [" ".join(command) for command in commands]

    assert commands
    assert any("/etc/maxvpn/firewall.user" in command for command in flattened)
    assert any("/etc/hotplug.d/iface/99-lan-vpn" in command for command in flattened)
    assert any("/usr/bin/vpn-lan-vless-on" in command for command in flattened)
    assert any("/usr/bin/maxvpn-vless-watchdog" in command for command in flattened)
    assert all("fw3" not in command for command in flattened)
    reload_service.reload.assert_not_called()
    assert flattened[-1].endswith("/etc/init.d/maxvpn-vless-watchdog enable")
    assert not flattened[-1].endswith(
        "maxvpn-vless-watchdog enable && /etc/init.d/maxvpn-vless-watchdog start"
    )


def test_vless_runtime_support_stops_on_failed_file_install_command() -> None:
    executor = Mock(spec=RemoteCommandExecutor)
    executor.run.side_effect = [
        Mock(returncode=0, stdout="", stderr=""),
        Mock(returncode=1, stdout="", stderr="write failed"),
    ]
    persistence = OpenWrtFirewallPersistence(executor=executor)

    try:
        persistence.install_vless_runtime_support(_policy())
    except RuntimeError as exc:
        assert "write failed" in str(exc)
    else:
        raise AssertionError("expected support installation failure")

    assert executor.run.call_count == 2


def test_start_vless_watchdog_runs_init_start() -> None:
    executor = Mock(spec=RemoteCommandExecutor)
    executor.run.return_value = Mock(returncode=0, stdout="", stderr="")
    persistence = OpenWrtFirewallPersistence(executor=executor)

    persistence.start_vless_watchdog()

    executor.run.assert_called_once_with(["/etc/init.d/maxvpn-vless-watchdog", "start"])
