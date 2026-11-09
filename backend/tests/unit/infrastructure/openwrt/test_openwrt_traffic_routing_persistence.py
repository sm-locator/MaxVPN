import subprocess
from unittest.mock import Mock

import pytest
from backend.infrastructure.openwrt.openwrt_traffic_routing_persistence import (
    OpenWrtTrafficRoutingPersistence,
    TrafficRoutingPersistenceSnapshot,
)
from backend.models.traffic_routing_policy import (
    TrafficRoutingPolicy,
)
from backend.models.traffic_routing_rule import (
    TrafficAddressFamily,
    TrafficRoute,
    TrafficRoutingRule,
    TrafficTargetType,
)
from backend.ports.remote_command_executor import RemoteCommandExecutor


def make_executor() -> Mock:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.return_value = Mock(
        returncode=0,
        stdout="",
        stderr="",
    )

    return executor


def make_policy() -> TrafficRoutingPolicy:
    return TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="1.1.1.1/32",
                action=TrafficRoute.DIRECT,
                priority=100,
            ),
        ],
    )


def test_build_install_commands_writes_restore_script() -> None:
    executor = make_executor()

    persistence = OpenWrtTrafficRoutingPersistence(
        executor=executor,
    )

    commands = persistence.build_install_commands(
        make_policy(),
    )

    assert len(commands) == 4

    write_command = commands[0][2]

    assert "printf '%s\\n'" in write_command
    assert "/etc/maxvpn/traffic-routing.restore" in write_command
    assert "MAXVPN_DIRECT" in write_command
    assert "1.1.1.1/32" in write_command
    assert "ip rule add priority 100" in write_command
    assert "fwmark 0x64/0xff table 200" in write_command


def test_install_and_uninstall_never_touch_awg_table_100() -> None:
    executor = make_executor()

    persistence = OpenWrtTrafficRoutingPersistence(
        executor=executor,
    )

    install_commands = persistence.build_install_commands(
        make_policy(),
    )
    uninstall_commands = persistence.build_uninstall_commands()

    install_text = "\\n".join(
        command[2] for command in install_commands if len(command) >= 3
    )
    uninstall_text = "\\n".join(
        command[2] for command in uninstall_commands if len(command) >= 3
    )

    assert "table 100" not in install_text
    assert "lookup 100" not in install_text

    assert "table 100" not in uninstall_text
    assert "lookup 100" not in uninstall_text

    assert "table 200" in install_text
    assert "table 200" in uninstall_text


def test_build_install_commands_sets_restore_script_executable() -> None:
    executor = make_executor()

    persistence = OpenWrtTrafficRoutingPersistence(
        executor=executor,
    )

    commands = persistence.build_install_commands(
        make_policy(),
    )

    assert commands[1] == [
        "chmod",
        "755",
        "/etc/maxvpn/traffic-routing.restore",
    ]


def test_build_install_commands_installs_firewall_hook() -> None:
    executor = make_executor()

    persistence = OpenWrtTrafficRoutingPersistence(
        executor=executor,
    )

    commands = persistence.build_install_commands(
        make_policy(),
    )

    hook_command = commands[2][2]

    assert "MAXVPN TRAFFIC ROUTING HOOK" in hook_command
    assert "/etc/maxvpn/traffic-routing.restore" in hook_command
    assert "sed -i" in hook_command


def test_build_install_commands_runs_restore_script_immediately() -> None:
    executor = make_executor()

    persistence = OpenWrtTrafficRoutingPersistence(
        executor=executor,
    )

    commands = persistence.build_install_commands(
        make_policy(),
    )

    assert commands[3] == [
        "sh",
        "-c",
        "/etc/maxvpn/traffic-routing.restore",
    ]


def test_restore_script_creates_dns_direct_ipset_without_flushing_it() -> None:
    executor = make_executor()

    persistence = OpenWrtTrafficRoutingPersistence(
        executor=executor,
    )

    commands = persistence.build_install_commands(
        make_policy(),
    )

    script = commands[0][2]

    create_direct = (
        "ipset create MAXVPN_DIRECT hash:ip "
        "family inet hashsize 1024 maxelem 65536 "
        "2>/dev/null || true"
    )

    assert create_direct in script
    assert "ipset flush MAXVPN_DIRECT\n" not in script
    assert "ipset flush MAXVPN_DIRECT_STATIC" in script


def test_build_restore_script_contains_ipv4_and_ipv6_ipsets() -> None:
    executor = make_executor()

    persistence = OpenWrtTrafficRoutingPersistence(
        executor=executor,
    )

    commands = persistence.build_install_commands(
        make_policy(),
    )

    script = commands[0][2]

    assert (
        "ipset create MAXVPN_DIRECT hash:ip family inet hashsize 1024 maxelem 65536"
    ) in script
    assert (
        "ipset create MAXVPN_DIRECT6 hash:ip family inet6 hashsize 1024 maxelem 65536"
    ) in script


def test_build_uninstall_commands_remove_hook_runtime_and_script() -> None:
    executor = make_executor()

    persistence = OpenWrtTrafficRoutingPersistence(
        executor=executor,
    )

    commands = persistence.build_uninstall_commands()

    assert len(commands) == 3

    remove_hook_command = commands[0][2]
    remove_runtime_command = commands[1][2]

    assert "MAXVPN TRAFFIC ROUTING HOOK" in (remove_hook_command)
    assert "sed -i" in remove_hook_command

    assert "iptables -t mangle -D PREROUTING" in (remove_runtime_command)
    assert "ip rule del priority 100" in remove_runtime_command
    assert "ip route flush table 200" in remove_runtime_command
    assert "ipset destroy MAXVPN_DIRECT_STATIC" in remove_runtime_command
    assert "ipset destroy MAXVPN_DIRECT 2>/dev/null" not in remove_runtime_command

    assert commands[2] == [
        "rm",
        "-f",
        "/etc/maxvpn/traffic-routing.restore",
    ]


def test_install_executes_all_commands() -> None:
    executor = make_executor()

    persistence = OpenWrtTrafficRoutingPersistence(
        executor=executor,
    )

    commands = persistence.build_install_commands(
        make_policy(),
    )

    persistence.install(make_policy())

    assert executor.run.call_count == len(commands)


def test_uninstall_executes_all_commands() -> None:
    executor = make_executor()

    persistence = OpenWrtTrafficRoutingPersistence(
        executor=executor,
    )

    commands = persistence.build_uninstall_commands()

    persistence.uninstall()

    assert executor.run.call_count == len(commands)


def test_install_raises_when_persistence_command_fails() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.return_value = Mock(
        returncode=1,
        stdout="",
        stderr="permission denied",
    )

    persistence = OpenWrtTrafficRoutingPersistence(
        executor=executor,
    )

    with pytest.raises(
        RuntimeError,
        match="traffic routing persistence command failed",
    ):
        persistence.install(make_policy())

    executor.run.assert_called_once()


def test_install_persists_only_ipv4_direct_cidr_rules() -> None:
    executor = make_executor()

    service = OpenWrtTrafficRoutingPersistence(
        executor=executor,
    )

    policy = TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="1.1.1.0/24",
                action=TrafficRoute.DIRECT,
                priority=100,
            ),
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="2001:db8::/32",
                action=TrafficRoute.DIRECT,
                priority=200,
                address_family=TrafficAddressFamily.IPV6,
            ),
            TrafficRoutingRule(
                target_type=TrafficTargetType.DOMAIN,
                target="example.com",
                action=TrafficRoute.DIRECT,
                priority=300,
            ),
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="10.0.0.0/8",
                action=TrafficRoute.VPN,
                priority=400,
            ),
        ],
    )

    commands = service.build_install_commands(policy)

    restore_script = commands[0][2]

    assert "ipset add MAXVPN_DIRECT_STATIC 1.1.1.0/24" in restore_script
    assert "2001:db8::/32" not in restore_script
    assert "example.com" not in restore_script
    assert "10.0.0.0/8" not in restore_script
    assert "table 200" in restore_script
    assert "table 100" not in restore_script


def test_install_empty_policy_keeps_maxvpn_runtime_structure() -> None:
    executor = make_executor()

    service = OpenWrtTrafficRoutingPersistence(
        executor=executor,
        lan_interface="br-lan",
        wan_interface="eth1",
        wan_gateway="46.48.56.1",
    )

    commands = service.build_install_commands(
        TrafficRoutingPolicy.from_rules([]),
    )

    restore_script = commands[0][2]

    assert "ipset flush MAXVPN_DIRECT_STATIC" in restore_script
    assert "ip route flush table 200" in restore_script
    assert "ip rule del priority 100" in restore_script
    assert "ip rule add priority 100 fwmark 0x64/0xff table 200" in restore_script

    assert "ipset add MAXVPN_DIRECT" not in restore_script
    assert "table 100" not in restore_script


def test_capture_snapshot_reads_existing_restore_script() -> None:
    executor = make_executor()
    executor.run.return_value.stdout = "#!/bin/sh\nprevious-state\n"

    service = OpenWrtTrafficRoutingPersistence(
        executor=executor,
        lan_interface="br-lan",
        wan_interface="eth1",
        wan_gateway="46.48.56.1",
    )

    snapshot = service.capture_snapshot()

    assert snapshot.restore_script == "#!/bin/sh\nprevious-state\n"


def test_capture_snapshot_detects_absent_restore_script() -> None:
    executor = make_executor()
    executor.run.return_value.returncode = 3

    service = OpenWrtTrafficRoutingPersistence(
        executor=executor,
        lan_interface="br-lan",
        wan_interface="eth1",
        wan_gateway="46.48.56.1",
    )

    snapshot = service.capture_snapshot()

    assert snapshot.restore_script is None


def test_restore_snapshot_reinstalls_previous_restore_script() -> None:
    executor = make_executor()

    service = OpenWrtTrafficRoutingPersistence(
        executor=executor,
        lan_interface="br-lan",
        wan_interface="eth1",
        wan_gateway="46.48.56.1",
    )

    snapshot = TrafficRoutingPersistenceSnapshot(
        restore_script="#!/bin/sh\nprevious-state\n",
    )

    service.restore_snapshot(snapshot)

    commands = [call.args[0] for call in executor.run.call_args_list]

    assert len(commands) == 3
    assert commands[0][0:2] == ["sh", "-c"]
    assert "/etc/maxvpn/traffic-routing.restore" in commands[0][2]
    assert commands[1] == [
        "chmod",
        "755",
        "/etc/maxvpn/traffic-routing.restore",
    ]
    assert commands[2][0:2] == ["sh", "-c"]
    assert "/etc/maxvpn/traffic-routing.restore" in commands[2][2]


def test_restore_snapshot_uninstalls_when_previous_state_is_absent() -> None:
    executor = make_executor()

    service = OpenWrtTrafficRoutingPersistence(
        executor=executor,
        lan_interface="br-lan",
        wan_interface="eth1",
        wan_gateway="46.48.56.1",
    )

    snapshot = TrafficRoutingPersistenceSnapshot(
        restore_script=None,
    )

    service.restore_snapshot(snapshot)

    commands = [call.args[0] for call in executor.run.call_args_list]

    assert len(commands) == 3
    assert any(
        "/etc/maxvpn/traffic-routing.restore" in command[2]
        for command in commands
        if len(command) >= 3
    )


def test_ipv4_mangle_commands_use_exact_current_format() -> None:
    executor = make_executor()

    persistence = OpenWrtTrafficRoutingPersistence(
        executor=executor,
        lan_interface="br-lan",
        wan_interface="eth1",
        wan_gateway="46.48.56.1",
    )

    install_commands = persistence.build_install_commands(
        make_policy(),
    )
    restore_script = install_commands[0][2]

    remove_runtime_command = persistence.build_uninstall_commands()[1][2]

    expected_restore_deletes = (
        "while iptables -t mangle -D PREROUTING "
        "-i br-lan "
        "-m set --match-set MAXVPN_DIRECT dst "
        "-j MARK --set-xmark 0x64/0xff "
        "2>/dev/null; do :; done",
        "while iptables -t mangle -D PREROUTING "
        "-i br-lan "
        "-m set --match-set MAXVPN_DIRECT dst "
        "-j MARK --set-mark 0x64 "
        "2>/dev/null; do :; done",
        "while iptables -t mangle -D PREROUTING "
        "-i br-lan "
        "-m set --match-set MAXVPN_DIRECT_STATIC dst "
        "-j MARK --set-xmark 0x64/0xff "
        "2>/dev/null; do :; done",
        "while iptables -t mangle -D PREROUTING "
        "-i br-lan "
        "-m set --match-set MAXVPN_DIRECT_STATIC dst "
        "-j MARK --set-mark 0x64 "
        "2>/dev/null; do :; done",
    )

    expected_restore_inserts = (
        "iptables -t mangle -I PREROUTING 1 "
        "-i br-lan "
        "-m set --match-set MAXVPN_DIRECT dst "
        "-j MARK --set-xmark 0x64/0xff",
        "iptables -t mangle -I PREROUTING 1 "
        "-i br-lan "
        "-m set --match-set MAXVPN_DIRECT_STATIC dst "
        "-j MARK --set-xmark 0x64/0xff",
    )

    for expected in expected_restore_deletes:
        assert expected in restore_script

    for expected in expected_restore_inserts:
        assert expected in restore_script
        assert restore_script.count(expected) == 1

    for expected in expected_restore_deletes:
        assert expected in remove_runtime_command

    forbidden_fragments = (
        "set--match-set",
        "--set-mark0x",
        "0x642>/dev/null",
    )

    for fragment in forbidden_fragments:
        assert fragment not in restore_script
        assert fragment not in remove_runtime_command


def test_restore_script_contains_dual_stack_ipv6_runtime_path() -> None:
    executor = make_executor()
    service = OpenWrtTrafficRoutingPersistence(
        executor=executor,
        lan_interface="br-lan",
        wan_interface="eth1",
        wan_gateway="46.48.56.1",
    )

    script = service.build_install_commands(TrafficRoutingPolicy.from_rules([]))[0][2]

    assert (
        "ipset create MAXVPN_DIRECT6 hash:ip family inet6 hashsize 1024 maxelem 65536"
    ) in script

    assert (
        "ip6tables -t mangle -D PREROUTING "
        "-i br-lan -m set --match-set MAXVPN_DIRECT6 dst "
        "-j MARK --set-mark 0x64"
    ) in script

    assert 'ipv6_default="$(ip -6 route show table main default' in script
    assert 'ip -6 addr show dev "$ipv6_dev" scope global' in script
    assert "ip -6 route flush table 200" in script
    assert "ip -6 rule del priority 100" in script
    assert "ip -6 rule add priority 100 fwmark 0x64/0xff table 200" in script

    assert (
        'ip -6 route add table 200 default via "$ipv6_gateway" dev "$ipv6_dev"'
    ) in script

    assert (
        "ip6tables -t mangle -I PREROUTING 1 "
        "-i br-lan -m set --match-set MAXVPN_DIRECT6 dst "
        "-j MARK --set-mark 0x64"
    ) in script

    assert "table 100" not in script
    assert "lookup 100" not in script


def test_restore_script_disables_ipv6_policy_path_without_global_ipv6() -> None:
    executor = make_executor()
    service = OpenWrtTrafficRoutingPersistence(
        executor=executor,
        lan_interface="br-lan",
        wan_interface="eth1",
        wan_gateway="46.48.56.1",
    )

    script = service.build_install_commands(TrafficRoutingPolicy.from_rules([]))[0][2]

    conditional_start = (
        'if [ -n "$ipv6_default" ] && [ -n "$ipv6_dev" ] && '
        'ip -6 addr show dev "$ipv6_dev" scope global | grep -q "inet6 "; then'
    )

    assert conditional_start in script

    before_if, inside_if = script.split(conditional_start, 1)
    ipv6_policy = inside_if.split("\nfi", 1)[0]

    assert "ip -6 route flush table 200" in before_if
    assert "ip -6 rule del priority 100" in before_if
    assert "ip6tables -t mangle -D PREROUTING" in before_if

    assert "ip -6 rule add priority 100" in ipv6_policy
    assert "ip6tables -t mangle -I PREROUTING" in ipv6_policy
    assert "ip -6 route add table 200 default" in ipv6_policy


def test_uninstall_removes_ipv6_runtime_and_direct_ipset() -> None:
    executor = make_executor()
    service = OpenWrtTrafficRoutingPersistence(executor=executor)

    remove_runtime_command = service.build_uninstall_commands()[1][2]

    assert (
        "ip6tables -t mangle -D PREROUTING "
        "-i br-lan -m set --match-set MAXVPN_DIRECT6 dst "
        "-j MARK --set-mark 0x64"
    ) in remove_runtime_command

    assert "ip -6 rule del priority 100" in remove_runtime_command
    assert "ip -6 route flush table 200" in remove_runtime_command
    assert "ipset destroy MAXVPN_DIRECT6 2>/dev/null || true" in remove_runtime_command

    assert "table 100" not in remove_runtime_command
    assert "lookup 100" not in remove_runtime_command


def test_restore_script_is_valid_shell() -> None:
    executor = make_executor()
    service = OpenWrtTrafficRoutingPersistence(executor=executor)

    restore_script = service.build_install_commands(
        TrafficRoutingPolicy.from_rules([])
    )[0][2]

    result = subprocess.run(
        ["sh", "-n"],
        input=restore_script,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_restore_script_contains_exact_dual_stack_ipv6_runtime_path() -> None:
    executor = make_executor()

    persistence = OpenWrtTrafficRoutingPersistence(
        executor=executor,
        lan_interface="br-lan",
        wan_interface="eth1",
        wan_gateway="46.48.56.1",
    )

    commands = persistence.build_install_commands(
        make_policy(),
    )

    script = commands[0][2]

    expected_lines = (
        'ipv6_default="$(ip -6 route show table main default | head -n 1)"',
        'ipv6_dev="$(printf "%s\\n" "$ipv6_default" | '
        'sed -n "s/.*dev \\([^ ]*\\).*/\\1/p")"',
        'if [ -n "$ipv6_default" ] && [ -n "$ipv6_dev" ] && '
        'ip -6 addr show dev "$ipv6_dev" scope global | '
        'grep -q "inet6 "; then',
        "    ip -6 route show table main | "
        "while IFS= read -r route; do "
        'case "$route" in '
        'default\\ *|"") continue ;; '
        "esac; "
        "ip -6 route add $route table 200 "
        "2>/dev/null || true; "
        "done",
        '    ipv6_gateway="$(printf "%s\\n" "$ipv6_default" '
        '| sed -n "s/.*via \\([^ ]*\\).*/\\1/p")"',
        "        ip -6 route add table 200 default via "
        '"$ipv6_gateway" dev "$ipv6_dev" 2>/dev/null || true',
        '        ip -6 route add table 200 default dev "$ipv6_dev" 2>/dev/null || true',
        "    ip6tables -t mangle -I PREROUTING 1 "
        "-i br-lan "
        "-m set --match-set MAXVPN_DIRECT6 dst "
        "-j MARK --set-mark 0x64",
        "    ip -6 rule add priority 100 fwmark 0x64/0xff table 200",
    )

    for expected in expected_lines:
        assert expected in script


def test_restore_script_has_no_malformed_ipv6_fragments() -> None:
    executor = make_executor()

    persistence = OpenWrtTrafficRoutingPersistence(
        executor=executor,
        lan_interface="br-lan",
        wan_interface="eth1",
        wan_gateway="46.48.56.1",
    )

    commands = persistence.build_install_commands(
        make_policy(),
    )

    script = commands[0][2]

    forbidden_fragments = (
        "tablemain",
        "sed-n",
        "ip -6addr",
        "set--match-set",
        "table200",
        "||true",
        'grep -q"inet6',
        'dev "$ipv6_dev"2>/dev/null',
        "fwmark 0x64/0xff table200",
    )

    for fragment in forbidden_fragments:
        assert fragment not in script, fragment


def test_restore_script_is_valid_shell_and_uninstall_cleans_ipv6_runtime() -> None:
    executor = make_executor()

    persistence = OpenWrtTrafficRoutingPersistence(
        executor=executor,
        lan_interface="br-lan",
        wan_interface="eth1",
        wan_gateway="46.48.56.1",
    )

    install_commands = persistence.build_install_commands(
        make_policy(),
    )

    script = install_commands[0][2]

    result = subprocess.run(
        ["sh", "-n"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    uninstall_commands = persistence.build_uninstall_commands()

    uninstall_text = "\n".join(
        command[2] for command in uninstall_commands if len(command) >= 3
    )

    assert "ip6tables -t mangle -D PREROUTING" in uninstall_text
    assert "MAXVPN_DIRECT6" in uninstall_text
    assert "ip -6 rule del priority 100" in uninstall_text
    assert "ip -6 route flush table 200" in uninstall_text
