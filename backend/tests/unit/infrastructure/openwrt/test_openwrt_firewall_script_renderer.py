from backend.infrastructure.openwrt.openwrt_firewall_script_renderer import (
    OpenWrtFirewallScriptRenderer,
)
from backend.models.vpn_traffic_policy import VpnTrafficPolicy


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


def test_render_allows_marked_direct_ipv4_traffic() -> None:
    renderer = OpenWrtFirewallScriptRenderer()

    script = renderer.render(make_policy())

    assert (
        "iptables -A MAXVPN_LAN_FORWARD "
        "-i br-lan -o eth1 "
        "-m mark --mark 0x64/0xff "
        "-j ACCEPT"
    ) in script

    assert ("iptables -A MAXVPN_LAN_FORWARD -i br-lan -o eth1 -j DROP") in script


def test_render_has_vless_ipv4_tun_and_direct_rules() -> None:
    script = OpenWrtFirewallScriptRenderer().render(make_policy())

    assert 'elif [ "$RUNTIME_MODE" = "vless" ]; then' in script
    assert "-i br-lan -o maxvpn0 -j ACCEPT" in script
    assert "-i br-lan -o eth1 -m mark --mark 0x64/0xff -j ACCEPT" in script
    assert "-i br-lan -o eth1 -j DROP" in script


def test_render_blocks_ipv6_forwarding_in_vless_mode() -> None:
    script = OpenWrtFirewallScriptRenderer().render(make_policy())
    ipv6_script = script.split("ip6tables -N MAXVPN_LAN6_FORWARD", 1)[1]

    assert 'if [ "$RUNTIME_MODE" = "vless" ]; then' in ipv6_script
    assert "ip6tables -A MAXVPN_LAN6_FORWARD -i br-lan -j DROP" in ipv6_script


def test_render_adds_direct_nat() -> None:
    renderer = OpenWrtFirewallScriptRenderer()

    script = renderer.render(make_policy())

    assert "iptables -t nat -N MAXVPN_DIRECT_NAT" in script
    assert "iptables -t nat -F MAXVPN_DIRECT_NAT" in script
    assert (
        "iptables -t nat -A MAXVPN_DIRECT_NAT "
        "-o eth1 "
        "-m mark --mark 0x64/0xff "
        "-j MASQUERADE"
    ) in script
    assert (
        "while iptables -t nat -D POSTROUTING "
        "-j MAXVPN_DIRECT_NAT 2>/dev/null; do :; done"
    ) in script
    assert ("iptables -t nat -I POSTROUTING 1 -j MAXVPN_DIRECT_NAT") in script


def test_render_contains_script_header() -> None:
    renderer = OpenWrtFirewallScriptRenderer()

    script = renderer.render(make_policy())

    assert script.startswith("#!/bin/sh\n")
    assert "set -eu" in script
    assert script.endswith("exit 0\n")


def test_render_contains_ipv4_chain_and_rules() -> None:
    renderer = OpenWrtFirewallScriptRenderer()

    script = renderer.render(make_policy())

    assert "iptables -N MAXVPN_LAN_FORWARD 2>/dev/null || true" in script
    assert "iptables -F MAXVPN_LAN_FORWARD" in script

    assert "iptables -A MAXVPN_LAN_FORWARD -i br-lan -o WireGuard -j ACCEPT" in script

    assert "iptables -A MAXVPN_LAN_FORWARD -i br-lan -o eth1 -j DROP" in script

    assert "iptables -A MAXVPN_LAN_FORWARD -j RETURN" in script


def test_render_contains_ipv6_chain_and_rules() -> None:
    renderer = OpenWrtFirewallScriptRenderer()

    script = renderer.render(make_policy())

    assert "ip6tables -N MAXVPN_LAN6_FORWARD 2>/dev/null || true" in script
    assert "ip6tables -F MAXVPN_LAN6_FORWARD" in script

    assert "ip6tables -A MAXVPN_LAN6_FORWARD -i br-lan -o WireGuard -j ACCEPT" in script

    assert "ip6tables -A MAXVPN_LAN6_FORWARD -i br-lan -o eth1 -j DROP" in script

    assert "ip6tables -A MAXVPN_LAN6_FORWARD -j RETURN" in script


def test_render_attaches_ipv4_chain_to_forwarding_rule() -> None:
    renderer = OpenWrtFirewallScriptRenderer()

    script = renderer.render(make_policy())

    assert (
        "while iptables -D forwarding_rule "
        "-j MAXVPN_LAN_FORWARD 2>/dev/null; do :; done" in script
    )
    assert (
        'iptables -I forwarding_rule "$POLICY_POSITION" -j MAXVPN_LAN_FORWARD' in script
    )


def test_render_attaches_ipv6_chain_to_forwarding_rule() -> None:
    renderer = OpenWrtFirewallScriptRenderer()

    script = renderer.render(make_policy())

    assert (
        "while ip6tables -D forwarding_rule "
        "-j MAXVPN_LAN6_FORWARD 2>/dev/null; do :; done" in script
    )
    assert (
        'ip6tables -I forwarding_rule "$POLICY_POSITION" '
        "-j MAXVPN_LAN6_FORWARD" in script
    )


def test_render_keeps_ipv6_wan_only_in_wan_mode_and_blocks_vless() -> None:
    renderer = OpenWrtFirewallScriptRenderer()
    script = renderer.render(make_policy())
    ipv6_script = script.split("ip6tables -N MAXVPN_LAN6_FORWARD", 1)[1]

    assert 'if [ "$RUNTIME_MODE" = "vless" ]; then' in ipv6_script
    assert 'elif [ "$RUNTIME_MODE" = "wan" ]; then' in ipv6_script
    assert "ip6tables -A MAXVPN_LAN6_FORWARD -i br-lan -o eth1 -j ACCEPT" in ipv6_script
    assert "ip6tables -A MAXVPN_LAN6_FORWARD -i br-lan -j DROP" in ipv6_script


def test_render_uses_custom_interfaces() -> None:
    renderer = OpenWrtFirewallScriptRenderer()

    policy = VpnTrafficPolicy(
        lan_interface="lan0",
        vpn_interface="wg0",
        wan_interface="wan0",
        allow_lan_to_vpn=True,
        allow_lan_to_wan=False,
        allow_lan_to_wan_ipv6=False,
        allow_vpn_endpoint_via_wan=True,
    )

    script = renderer.render(policy)

    assert "-i lan0 -o wg0 -j ACCEPT" in script
    assert "-i lan0 -o wan0 -j DROP" in script


def test_render_uses_wan_mode_runtime_switch() -> None:
    renderer = OpenWrtFirewallScriptRenderer()

    script = renderer.render(make_policy())

    assert 'RUNTIME_MODE_FILE="/etc/maxvpn/runtime-mode"' in script
    assert 'RUNTIME_MODE="vpn"' in script
    assert (
        '[ "$RUNTIME_MODE" = "wan" ] || '
        '[ "$RUNTIME_MODE" = "vless" ] || RUNTIME_MODE="vpn"' in script
    )
    assert 'if [ "$RUNTIME_MODE" = "wan" ]; then' in script
    assert "iptables -A MAXVPN_LAN_FORWARD -i br-lan -o eth1 -j ACCEPT" in script
    assert "iptables -A MAXVPN_LAN_FORWARD -i br-lan -o eth1 -j DROP" in script


def test_render_installs_ipv4_and_ipv6_update_guards_before_chain_flush() -> None:
    script = OpenWrtFirewallScriptRenderer().render(make_policy())

    ipv4_guard = script.index(
        "iptables -I forwarding_rule 1 -j MAXVPN_FIREWALL_UPDATE_GUARD"
    )
    ipv4_flush = script.index("iptables -F MAXVPN_LAN_FORWARD")
    ipv6_guard = script.index(
        "ip6tables -I forwarding_rule 1 -j MAXVPN6_FW_UPDATE_GUARD"
    )
    ipv6_flush = script.index("ip6tables -F MAXVPN_LAN6_FORWARD")

    assert ipv4_guard < ipv4_flush
    assert ipv6_guard < ipv6_flush


def test_render_removes_update_guards_only_after_direct_nat_and_ipv6_policy() -> None:
    script = OpenWrtFirewallScriptRenderer().render(make_policy())

    nat_jump = script.index("iptables -t nat -I POSTROUTING 1 -j MAXVPN_DIRECT_NAT")
    ipv4_cleanup = script.index("remove_update_guard() {")
    ipv6_cleanup = script.index("remove_update_guard ip6tables MAXVPN6_FW_UPDATE_GUARD")
    ipv6_policy = script.index("ip6tables -A MAXVPN_LAN6_FORWARD -j RETURN")

    assert nat_jump < ipv4_cleanup
    assert ipv6_policy < ipv4_cleanup
    assert nat_jump < ipv6_cleanup


def test_render_shell_syntax_is_valid() -> None:
    import subprocess

    script = OpenWrtFirewallScriptRenderer().render(make_policy())
    result = subprocess.run(
        ["sh", "-n"], input=script, text=True, capture_output=True, check=False
    )

    assert result.returncode == 0, result.stderr


def test_render_keeps_update_guards_when_active_chain_flush_fails(tmp_path) -> None:
    import os
    import subprocess

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "commands.log"
    stub = """#!/bin/sh
printf '%s %s\n' "$(basename "$0")" "$*" >> "$MAXVPN_TEST_LOG"
if [ "$1" = "-C" ]; then
    exit 1
fi
if [ "$1" = "-F" ] && [ "$2" = "MAXVPN_LAN_FORWARD" ]; then
    exit 47
fi
exit 0
"""
    for command in ("iptables", "ip6tables"):
        path = bin_dir / command
        path.write_text(stub)
        path.chmod(0o755)

    script = OpenWrtFirewallScriptRenderer().render(make_policy())
    script = script.replace(
        'RUNTIME_MODE_FILE="/etc/maxvpn/runtime-mode"',
        f'RUNTIME_MODE_FILE="{tmp_path / "runtime-mode"}"',
    )
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["MAXVPN_TEST_LOG"] = str(log_path)

    result = subprocess.run(
        ["sh"], input=script, text=True, capture_output=True, check=False, env=env
    )
    log = log_path.read_text()

    assert result.returncode == 47
    assert "iptables -I forwarding_rule 1 -j MAXVPN_FIREWALL_UPDATE_GUARD" in log
    assert "ip6tables -I forwarding_rule 1 -j MAXVPN6_FW_UPDATE_GUARD" in log
    assert "iptables -D forwarding_rule -j MAXVPN_FIREWALL_UPDATE_GUARD" not in log
    assert "ip6tables -D forwarding_rule -j MAXVPN6_FW_UPDATE_GUARD" not in log


def test_render_firewall_script_uses_shared_reentrant_runtime_lock() -> None:
    script = OpenWrtFirewallScriptRenderer().render(make_policy())

    lock = script.index('RUNTIME_LOCK_FILE="/tmp/maxvpn-runtime.lock"')
    mode_read = script.index('RUNTIME_MODE_FILE="/etc/maxvpn/runtime-mode"')
    assert lock < mode_read
    assert "flock -x 9" in script
    assert "export MAXVPN_RUNTIME_LOCK_HELD=1" in script
    assert "if ! ( : >&9 ) 2>/dev/null; then" in script


def test_render_keeps_guards_ahead_of_wan_policy_when_cleanup_inspection_fails(
    tmp_path,
) -> None:
    import os
    import subprocess

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "commands.log"
    stub = """#!/bin/sh
name=${0##*/}
echo "$name $*" >> "$MAXVPN_TEST_LOG"
if [ "$1" = "-t" ]; then shift 2; fi
case "$1" in
    -C|-D) exit 1 ;;
    -S)
        [ "$#" -gt 1 ] || exit 71
        if [ "$#" -eq 2 ] && [ "$2" = "forwarding_rule" ]; then
            case "$name" in
                iptables) guard=MAXVPN_MODE_TRANSITION_GUARD ;;
                ip6tables) guard=MAXVPN6_MODE_GUARD ;;
            esac
            echo "-A forwarding_rule -j $guard"
        fi
        ;;
    *) exit 0 ;;
esac
"""
    for command in ("iptables", "ip6tables"):
        path = bin_dir / command
        path.write_text(stub, encoding="utf-8")
        path.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["MAXVPN_TEST_LOG"] = str(log_path)

    script = (
        OpenWrtFirewallScriptRenderer()
        .render(make_policy())
        .replace(
            'RUNTIME_LOCK_FILE="/tmp/maxvpn-runtime.lock"',
            f'RUNTIME_LOCK_FILE="{tmp_path / "runtime.lock"}"',
        )
        .replace(
            'RUNTIME_MODE_FILE="/etc/maxvpn/runtime-mode"',
            f'RUNTIME_MODE_FILE="{tmp_path / "runtime-mode"}"',
        )
    )
    (tmp_path / "runtime-mode").write_text("wan\n")
    result = subprocess.run(
        ["sh"], input=script, text=True, capture_output=True, check=False, env=env
    )
    log = log_path.read_text()

    assert result.returncode == 1
    assert (
        "Unable to inspect firewall while removing MAXVPN_FIREWALL_UPDATE_GUARD"
        in result.stderr
    )
    assert "iptables -I forwarding_rule 1 -j MAXVPN_FIREWALL_UPDATE_GUARD" in log
    assert "ip6tables -I forwarding_rule 1 -j MAXVPN6_FW_UPDATE_GUARD" in log
    assert "iptables -D forwarding_rule -j MAXVPN_FIREWALL_UPDATE_GUARD" not in log
    assert "ip6tables -D forwarding_rule -j MAXVPN6_FW_UPDATE_GUARD" not in log

    for binary, transition_guard, policy_chain in (
        ("iptables", "MAXVPN_MODE_TRANSITION_GUARD", "MAXVPN_LAN_FORWARD"),
        ("ip6tables", "MAXVPN6_MODE_GUARD", "MAXVPN_LAN6_FORWARD"),
    ):
        guard_first = log.index(f"{binary} -I forwarding_rule 2 -j {transition_guard}")
        policy_next = log.index(f"{binary} -I forwarding_rule 3 -j {policy_chain}")
        assert guard_first < policy_next


def test_all_rendered_chain_names_fit_legacy_xtables_limit():
    import re

    from backend.infrastructure.openwrt.openwrt_lan_vpn_command_renderer import (
        OpenWrtLanVpnCommandRenderer,
    )

    commands = OpenWrtLanVpnCommandRenderer()
    scripts = [
        OpenWrtFirewallScriptRenderer().render(make_policy()),
        commands.render_on(),
        commands.render_off(),
        commands.render_vless_on(),
    ]
    for script in scripts:
        names = re.findall(r"\bMAXVPN[A-Z0-9_]*(?:GUARD|FORWARD|NAT)\b", script)
        assert names
        for name in names:
            # XT_EXTENSION_MAXNAMELEN includes the terminating NUL.
            assert len(name.encode("ascii")) <= 28, name
