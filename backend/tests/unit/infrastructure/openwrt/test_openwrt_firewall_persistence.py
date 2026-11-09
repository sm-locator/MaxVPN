from unittest.mock import Mock

import pytest
from backend.infrastructure.openwrt.openwrt_firewall_persistence import (
    OpenWrtFirewallPersistence,
)
from backend.infrastructure.openwrt.openwrt_firewall_verifier import (
    OpenWrtFirewallVerificationResult,
)
from backend.models.vpn_traffic_policy import VpnTrafficPolicy
from backend.ports.remote_command_executor import RemoteCommandExecutor
from backend.services.openwrt_firewall_reload import (
    OpenWrtFirewallReloadResult,
    OpenWrtFirewallReloadService,
)


def make_policy() -> VpnTrafficPolicy:
    return VpnTrafficPolicy(
        lan_interface="br-lan",
        vpn_interface="WireGuard",
        wan_interface="eth1",
        allow_lan_to_vpn=True,
        allow_lan_to_wan=False,
        allow_lan_to_wan_ipv6=False,
        allow_vpn_endpoint_via_wan=True,
    )


def healthy_verification() -> OpenWrtFirewallVerificationResult:
    return OpenWrtFirewallVerificationResult(
        healthy=True,
        ipv4_chain_exists=True,
        ipv6_chain_exists=True,
        ipv4_jump_count=1,
        ipv6_jump_count=1,
        ipv4_vpn_accept_rule=True,
        ipv4_wan_drop_rule=True,
        ipv6_vpn_accept_rule=True,
        ipv6_wan_drop_rule=True,
        reason=None,
    )


def healthy_reload_result(
    *,
    returncode: int = 0,
    reason: str | None = None,
) -> OpenWrtFirewallReloadResult:
    return OpenWrtFirewallReloadResult(
        reload_returncode=returncode,
        reload_succeeded=returncode == 0,
        verification=healthy_verification(),
        healthy=True,
        reason=reason,
    )


def find_command(
    commands: list[list[str]],
    predicate: callable,
) -> list[str]:
    for command in commands:
        if predicate(command):
            return command

    raise AssertionError("Matching command not found")


def command_text(command: list[str]) -> str:
    return " ".join(command)


def failed_reload_result() -> OpenWrtFirewallReloadResult:
    failed_verification_result = OpenWrtFirewallVerificationResult(
        healthy=False,
        ipv4_chain_exists=False,
        ipv6_chain_exists=True,
        ipv4_jump_count=0,
        ipv6_jump_count=1,
        ipv4_vpn_accept_rule=False,
        ipv4_wan_drop_rule=False,
        ipv6_vpn_accept_rule=True,
        ipv6_wan_drop_rule=True,
        reason="firewall_verification_failed: ipv4_chain_exists",
    )

    return OpenWrtFirewallReloadResult(
        reload_returncode=1,
        reload_succeeded=False,
        verification=failed_verification_result,
        healthy=False,
        reason="firewall_verification_failed: ipv4_chain_exists",
    )


def test_build_install_commands_installs_termux_vpn_on_off_scripts() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
    )

    commands = persistence.build_install_commands(make_policy())
    texts = [command_text(command) for command in commands]

    on_index = next(
        i for i, value in enumerate(texts) if "/usr/bin/vpn-lan-on" in value
    )
    off_index = next(
        i for i, value in enumerate(texts) if "/usr/bin/vpn-lan-off" in value
    )

    assert "vpn-lan-on" in texts[on_index]
    assert "vpn-lan-off" in texts[off_index]


def test_build_uninstall_commands_restores_termux_vpn_on_off_scripts() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
    )

    commands = persistence.build_uninstall_commands()
    texts = [command_text(command) for command in commands]

    on_restore = next(value for value in texts if "vpn-lan-on.backup" in value)
    off_restore = next(value for value in texts if "vpn-lan-off.backup" in value)

    assert "/usr/bin/vpn-lan-on" in on_restore
    assert "/usr/bin/vpn-lan-off" in off_restore


def test_build_install_commands_creates_backup_once() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
    )

    commands = persistence.build_install_commands(make_policy())

    backup_command = find_command(
        commands,
        lambda command: (
            command[:2] == ["sh", "-c"]
            and "firewall.user.backup" in command[2]
            and "cp /etc/firewall.user /etc/maxvpn/firewall.user.backup" in command[2]
        ),
    )

    assert backup_command[:2] == ["sh", "-c"]
    assert "firewall.user.backup" in backup_command[2]


def test_build_install_commands_writes_rendered_script() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
    )

    commands = persistence.build_install_commands(make_policy())

    write_command = find_command(
        commands,
        lambda command: (
            command[:2] == ["sh", "-c"]
            and "printf '%s\\n'" in command[2]
            and "> /etc/maxvpn/firewall.user" in command[2]
        ),
    )

    assert write_command[:2] == ["sh", "-c"]
    assert "printf '%s\\n'" in write_command[2]
    assert "> /etc/maxvpn/firewall.user" in write_command[2]
    assert "base64" not in write_command[2]


def test_build_install_commands_sets_executable_permission() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
    )

    commands = persistence.build_install_commands(make_policy())

    chmod_command = find_command(
        commands,
        lambda command: (
            command
            == [
                "chmod",
                "755",
                "/etc/maxvpn/firewall.user",
            ]
        ),
    )
    assert chmod_command == [
        "chmod",
        "755",
        "/etc/maxvpn/firewall.user",
    ]


def test_build_install_commands_replaces_existing_hook() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
    )

    commands = persistence.build_install_commands(make_policy())

    hook_command = find_command(
        commands,
        lambda command: command[:2] == ["sh", "-c"] and "start_count=" in command[2],
    )[2]

    assert "start_count=" in hook_command
    assert "end_count=" in hook_command
    assert "sed -i" in hook_command
    assert "MAXVPN FIREWALL HOOK" in hook_command
    assert "printf" in hook_command
    assert ">> /etc/firewall.user" in hook_command


def test_build_install_commands_rejects_invalid_marker_state() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
    )

    commands = persistence.build_install_commands(make_policy())

    hook_command = find_command(
        commands,
        lambda command: (
            command[:2] == ["sh", "-c"]
            and "Invalid MaxVPN firewall hook markers" in command[2]
        ),
    )[2]

    assert "echo 'Invalid MaxVPN firewall hook markers' >&2" in hook_command
    assert 'start_count" -gt 1' in hook_command
    assert 'end_count" -gt 1' in hook_command
    assert 'start_count" -ne "$end_count' in hook_command


def test_build_install_commands_is_safe_for_repeated_install() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
    )

    first = persistence.build_install_commands(make_policy())
    second = persistence.build_install_commands(make_policy())

    assert first == second


def test_build_uninstall_commands_remove_hook_safely() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
    )

    commands = persistence.build_uninstall_commands()

    remove_command = find_command(
        commands,
        lambda command: command[:2] == ["sh", "-c"] and "start_count=" in command[2],
    )[2]

    assert "start_count=" in remove_command
    assert "end_count=" in remove_command
    assert "sed -i" in remove_command
    assert "Invalid MaxVPN firewall hook markers" in remove_command
    assert "MAXVPN FIREWALL HOOK" in remove_command


def test_install_executes_commands_without_reload_service() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.return_value = Mock(
        stdout="",
        stderr="",
        returncode=0,
    )

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
    )

    commands = persistence.build_install_commands(make_policy())

    result = persistence.install(make_policy())

    assert result is None
    assert executor.run.call_count == len(commands)


def test_install_runs_semantic_reload_after_files_are_installed() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.return_value = Mock(
        stdout="",
        stderr="",
        returncode=0,
    )

    reload_service = Mock(spec=OpenWrtFirewallReloadService)
    reload_result = healthy_reload_result()

    reload_service.reload.return_value = reload_result

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
        reload_service=reload_service,
    )

    result = persistence.install(make_policy())

    assert result is reload_result
    reload_service.reload.assert_called_once_with()


def test_install_accepts_nonzero_fw3_when_runtime_state_is_healthy() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.return_value = Mock(
        stdout="",
        stderr="",
        returncode=0,
    )

    reload_service = Mock(spec=OpenWrtFirewallReloadService)

    reload_result = healthy_reload_result(
        returncode=1,
        reason="fw3_reload_returned_nonzero_but_maxvpn_firewall_is_healthy",
    )

    reload_service.reload.return_value = reload_result

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
        reload_service=reload_service,
    )

    result = persistence.install(make_policy())

    assert result is reload_result
    assert result.healthy is True
    assert result.degraded is True


def test_install_rejects_failed_runtime_verification() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.return_value = Mock(
        stdout="",
        stderr="",
        returncode=0,
    )

    reload_service = Mock(spec=OpenWrtFirewallReloadService)
    reload_service.reload.return_value = failed_reload_result()

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
        reload_service=reload_service,
    )

    with pytest.raises(
        RuntimeError,
        match="runtime verification",
    ):
        persistence.install(make_policy())

    reload_service.reload.assert_called_once_with()


def test_install_raises_when_file_command_fails_before_reload() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.return_value = Mock(
        stdout="",
        stderr="permission denied",
        returncode=1,
    )

    reload_service = Mock(spec=OpenWrtFirewallReloadService)

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
        reload_service=reload_service,
    )

    with pytest.raises(
        RuntimeError,
        match="OpenWrt firewall persistence command failed",
    ):
        persistence.install(make_policy())

    reload_service.reload.assert_not_called()
    executor.run.assert_called_once()


def test_uninstall_executes_all_commands() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.return_value = Mock(
        stdout="",
        stderr="",
        returncode=0,
    )

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
    )

    commands = persistence.build_uninstall_commands()

    persistence.uninstall()

    assert executor.run.call_count == len(commands)


def test_uninstall_raises_on_command_failure() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.return_value = Mock(
        stdout="",
        stderr="rm failed",
        returncode=1,
    )

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
    )

    with pytest.raises(
        RuntimeError,
        match="OpenWrt firewall persistence command failed",
    ):
        persistence.uninstall()

    executor.run.assert_called_once()


def test_build_install_commands_refreshes_existing_hook_instead_of_skipping() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
    )

    commands = persistence.build_install_commands(make_policy())

    hook_command = find_command(
        commands,
        lambda command: (
            command[:2] == ["sh", "-c"] and "start_count=$(grep -F -c" in command[2]
        ),
    )[2]

    assert "start_count=$(grep -F -c" in hook_command
    assert "end_count=$(grep -F -c" in hook_command
    assert 'if [ "$start_count" -eq 1 ]; then' in hook_command
    assert "sed -i '/^# >>> MAXVPN FIREWALL HOOK >>>$/," in hook_command
    assert "/^# <<< MAXVPN FIREWALL HOOK <<</d'" in hook_command
    assert 'printf "\\n%s\\n" "$hook"' in hook_command
    assert "grep -Fq" not in hook_command


def test_build_uninstall_commands_removes_ipv4_runtime_rules() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
    )

    commands = persistence.build_uninstall_commands()

    ipv4_command = find_command(
        commands,
        lambda command: (
            command[:2] == ["sh", "-c"]
            and "while iptables -D forwarding_rule" in command[2]
        ),
    )[2]

    assert "while iptables -D forwarding_rule" in ipv4_command
    assert "-j MAXVPN_LAN_FORWARD" in ipv4_command
    assert "iptables -F MAXVPN_LAN_FORWARD" in ipv4_command
    assert "iptables -X MAXVPN_LAN_FORWARD" in ipv4_command
    assert "MAXVPN IPv4 chain still exists" in ipv4_command
    assert "MAXVPN IPv4 jump still exists" in ipv4_command


def test_build_uninstall_commands_removes_ipv6_runtime_rules() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
    )

    commands = persistence.build_uninstall_commands()

    ipv6_command = find_command(
        commands,
        lambda command: (
            command[:2] == ["sh", "-c"]
            and "while ip6tables -D forwarding_rule" in command[2]
        ),
    )[2]

    assert "while ip6tables -D forwarding_rule" in ipv6_command
    assert "-j MAXVPN_LAN6_FORWARD" in ipv6_command
    assert "ip6tables -F MAXVPN_LAN6_FORWARD" in ipv6_command
    assert "ip6tables -X MAXVPN_LAN6_FORWARD" in ipv6_command
    assert "MAXVPN IPv6 chain still exists" in ipv6_command
    assert "MAXVPN IPv6 jump still exists" in ipv6_command


def test_build_install_commands_backups_firewall_user_reload_state() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
    )

    commands = persistence.build_install_commands(make_policy())

    backup_command = find_command(
        commands,
        lambda command: (
            command[:2] == ["sh", "-c"]
            and "uci show firewall" in command[2]
            and "firewall.user.reload.backup" in command[2]
        ),
    )[2]

    assert "uci show firewall" in backup_command
    assert "/etc/maxvpn/firewall.user.reload.backup" in backup_command
    assert "ABSENT" in backup_command
    assert "UNSET" in backup_command


def test_build_install_commands_ensures_firewall_user_reload() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
    )

    commands = persistence.build_install_commands(make_policy())

    reload_command = find_command(
        commands,
        lambda command: (
            command[:2] == ["sh", "-c"]
            and "uci show firewall" in command[2]
            and "prerouting" not in command[2]
            and "firewall.user.reload.backup" not in command[2]
            and "firewall.user" in command[2]
        ),
    )

    reload_text = command_text(reload_command)
    assert "uci show firewall" in reload_text
    assert "/etc/firewall.user" in reload_text
    assert 'uci set "$section.reload=1"' in reload_text
    assert "uci add firewall include" in reload_text
    assert "uci commit firewall" in reload_text


def test_build_uninstall_commands_restores_firewall_user_reload_state() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    persistence = OpenWrtFirewallPersistence(
        executor=executor,
    )

    commands = persistence.build_uninstall_commands()

    restore_command = find_command(
        commands,
        lambda command: (
            command[:2] == ["sh", "-c"]
            and "/etc/maxvpn/firewall.user.reload.backup" in command[2]
        ),
    )[2]

    assert "/etc/maxvpn/firewall.user.reload.backup" in restore_command
    assert "saved=$(cat /etc/maxvpn/firewall.user.reload.backup)" in (restore_command)
    assert 'uci set "$section.reload=$saved"' in restore_command
    assert 'uci delete "$section.reload"' in restore_command


def test_build_install_commands_installs_but_disables_vless_boot_restore() -> None:
    persistence = OpenWrtFirewallPersistence(executor=Mock(spec=RemoteCommandExecutor))
    texts = [
        command_text(command)
        for command in persistence.build_install_commands(make_policy())
    ]

    assert any(
        "/etc/init.d/maxvpn-vless-routing-restore" in value and "printf" in value
        for value in texts
    )
    assert any(
        "chmod 755 /etc/init.d/maxvpn-vless-routing-restore" in value for value in texts
    )
    assert any(
        "/etc/init.d/maxvpn-vless-routing-restore disable" in value for value in texts
    )
    assert any(
        "/usr/bin/maxvpn-vless-watchdog" in value and "printf" in value
        for value in texts
    )
    assert any("chmod 755 /usr/bin/maxvpn-vless-watchdog" in value for value in texts)
    assert any(
        "/etc/init.d/maxvpn-vless-watchdog" in value and "printf" in value
        for value in texts
    )
    assert any(
        "chmod 755 /etc/init.d/maxvpn-vless-watchdog" in value for value in texts
    )
    assert any("/etc/init.d/maxvpn-vless-watchdog enable" in value for value in texts)


def test_build_uninstall_commands_disables_and_restores_vless_boot_restore() -> None:
    persistence = OpenWrtFirewallPersistence(executor=Mock(spec=RemoteCommandExecutor))
    texts = [
        command_text(command) for command in persistence.build_uninstall_commands()
    ]

    assert any(
        "/etc/init.d/maxvpn-vless-routing-restore disable" in value for value in texts
    )
    assert any("maxvpn-vless-routing-restore.init.backup" in value for value in texts)
    assert any("/etc/init.d/maxvpn-vless-watchdog stop" in value for value in texts)
    assert any("/etc/init.d/maxvpn-vless-watchdog disable" in value for value in texts)
    assert any("maxvpn-vless-watchdog.backup" in value for value in texts)
    assert any("maxvpn-vless-watchdog.init.backup" in value for value in texts)
