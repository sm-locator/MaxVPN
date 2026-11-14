import pytest
from backend.infrastructure.openwrt.openwrt_lan_vpn_command_renderer import (
    OpenWrtLanVpnCommandRenderer,
)


def test_render_on_uses_transition_guards_before_switching_runtime_mode() -> None:
    script = OpenWrtLanVpnCommandRenderer().render_on()

    assert script.startswith("#!/bin/sh")
    guard_install = script.index("ensure_transition_guards || {")
    mode_write = script.index("printf '%s\\n' vpn > \"$RUNTIME_MODE_FILE\"")
    firewall_apply = script.index('"$FIREWALL" >/dev/null 2>&1 || {')
    wireguard_start = script.index("ifup WireGuard >/dev/null 2>&1 || {")
    hotplug_apply = script.index('ACTION=ifup INTERFACE=WireGuard "$HOTPLUG"')
    guard_remove = script.index("remove_transition_guards || {")

    assert guard_install < mode_write < firewall_apply < wireguard_start
    assert wireguard_start < hotplug_apply < guard_remove
    assert "MAXVPN_MODE_TRANSITION_GUARD" in script
    assert "MAXVPN6_MODE_GUARD" in script
    assert "MAXVPN_DIRECT_NAT" in script
    assert "WAN remains fail-closed" in script


def test_render_on_is_independent_of_maxvpn_api() -> None:
    script = OpenWrtLanVpnCommandRenderer().render_on()

    assert "127.0.0.1:8080" not in script
    assert "maxvpn-backend" not in script
    assert "/api/" not in script


def test_vless_rollback_verifies_previous_policy_before_releasing_guards() -> None:
    script = OpenWrtLanVpnCommandRenderer().render_vless_on()

    rollback_start = script.index("rollback_previous_mode() {")
    rollback_end = script.index("\n}", rollback_start)
    rollback = script[rollback_start:rollback_end]

    assert '"$FIREWALL" >/dev/null 2>&1 || return 1' in rollback
    assert (
        'ACTION=ifup INTERFACE=br-lan "$HOTPLUG" >/dev/null 2>&1 || return 1'
        in rollback
    )
    assert "verify_previous_mode || return 1" in rollback
    assert "remove_transition_guards || return 1" in rollback
    assert rollback.index("verify_previous_mode || return 1") < rollback.index(
        "remove_transition_guards || return 1"
    )
    assert "rollback incomplete, transition guards retained" in script


def test_verify_previous_mode_covers_wan_vpn_and_vless() -> None:
    script = OpenWrtLanVpnCommandRenderer().render_vless_on()

    verify_start = script.index("verify_previous_mode() {")
    verify_end = script.index("\n}", verify_start)
    verify = script[verify_start:verify_end]

    assert "wan)" in verify
    assert "vpn)" in verify
    assert "vless)" in verify
    assert "^default dev WireGuard" in verify
    assert "^default dev maxvpn0" in verify
    assert "to $DNS_IP lookup 100" in verify


def test_render_vless_on_is_fail_closed_and_verifies_tun() -> None:
    script = OpenWrtLanVpnCommandRenderer().render_vless_on()

    guard_install = script.index("ensure_transition_guards || {")
    mode_write = script.index("printf '%s\\n' vless > \"$RUNTIME_MODE_FILE\"")
    guard_remove = script.index("remove_transition_guards || {")
    runtime_verify = script.index("grep -q '^vless$' \"$RUNTIME_MODE_FILE\"")
    assert guard_install < mode_write < runtime_verify < guard_remove
    assert "MAXVPN_MODE_TRANSITION_GUARD" in script
    assert "MAXVPN6_MODE_GUARD" in script

    assert '"$SING_BOX" check -c "$SING_BOX_CONFIG"' in script
    assert "grep -q 'UP'" in script
    assert "vless >" in script
    assert 'ACTION=ifup INTERFACE=maxvpn0 "$HOTPLUG"' in script
    assert "default dev maxvpn0" in script
    assert "previous mode restored" in script
    assert "iptables -C forwarding_rule -j MAXVPN_LAN_FORWARD" in script
    assert "ip6tables -C forwarding_rule -j MAXVPN_LAN6_FORWARD" in script


def test_render_vless_restore_init_waits_for_sing_box_in_vless_mode() -> None:
    script = OpenWrtLanVpnCommandRenderer().render_vless_restore_init()

    assert script.startswith("#!/bin/sh /etc/rc.common")
    assert "START=99" in script
    assert "USE_PROCD" not in script
    assert "start() {" in script
    assert "start_service()" not in script
    assert '"$mode" = "vless"' in script
    assert '"$SING_BOX" check -c "$SING_BOX_CONFIG"' in script
    assert "pidof sing-box" in script
    assert 'ip link show "$VLESS_IF"' in script
    assert 'if MAXVPN_EXPECT_RUNTIME_MODE=vless "$VLESS_ON"; then' in script
    assert "VLESS LAN routes restored after boot" in script
    assert "keeping fail-closed policy" in script


def test_render_vless_watchdog_repairs_missing_policy_only_in_vless_mode() -> None:
    script = OpenWrtLanVpnCommandRenderer().render_vless_watchdog()

    assert script.startswith("#!/bin/sh")
    assert '"$mode" = "vless"' not in script  # mode is checked before component repair
    assert '"$mode" != "vless"' in script
    assert "while :; do" in script
    assert "policy_is_healthy()" in script
    assert "^default dev maxvpn0" in script
    assert "to $DNS_IP lookup 100" in script
    assert "MAXVPN_LAN_FORWARD" in script
    assert "MAXVPN_LAN6_FORWARD" in script
    assert 'if MAXVPN_EXPECT_RUNTIME_MODE=vless "$VLESS_ON"; then' in script
    assert "VLESS policy repaired" in script
    assert "sleep 5" in script


def test_render_vless_watchdog_recovers_missing_process_or_tun_with_cooldown() -> None:
    script = OpenWrtLanVpnCommandRenderer().render_vless_watchdog()

    assert "SING_BOX_INIT=/etc/init.d/maxvpn-sing-box" in script
    assert "vless_components_healthy()" in script
    assert "pidof sing-box >/dev/null 2>&1" in script
    assert 'ip link show "$VLESS_IF"' in script
    assert "FAILURE_THRESHOLD=3" in script
    assert "RESTART_COOLDOWN_TICKS=6" in script
    assert "SERVICE_ACTION=restart" in script
    assert "SERVICE_ACTION=start" in script
    assert '"$SING_BOX_INIT" "$SERVICE_ACTION"' in script
    assert "wait_for_vless_components" in script
    assert "within 20 seconds" in script
    assert "fail-closed policy retained" in script
    assert '"$(cat "$RUNTIME_MODE_FILE" 2>/dev/null || true)" = "vless"' in script


def test_render_vless_watchdog_does_not_restart_on_invalid_config() -> None:
    script = OpenWrtLanVpnCommandRenderer().render_vless_watchdog()

    config_check = script.index('elif ! "$SING_BOX" check -c "$SING_BOX_CONFIG"')
    service_action = script.index('if "$SING_BOX_INIT" "$SERVICE_ACTION"; then')
    assert config_check < service_action
    assert "refusing restart; fail-closed policy retained" in script


def test_render_vless_watchdog_init_uses_procd_supervision() -> None:
    script = OpenWrtLanVpnCommandRenderer().render_vless_watchdog_init()

    assert script.startswith("#!/bin/sh /etc/rc.common")
    assert "START=99" in script
    assert "USE_PROCD=1" in script
    assert 'procd_set_param command "$WATCHDOG"' in script
    assert "procd_set_param respawn" in script


def test_render_off_switches_to_wan_before_stopping_wireguard() -> None:
    script = OpenWrtLanVpnCommandRenderer().render_off()

    wan_ipv4_verify = script.index("WAN IPv4 allow rule verification failed")
    wan_ipv6_verify = script.index("WAN IPv6 allow rule verification failed")
    guard_remove = script.index("remove_transition_guards || {")
    assert wan_ipv4_verify < guard_remove
    assert wan_ipv6_verify < guard_remove

    mode_index = script.index("printf '%s\\n' wan")
    firewall_index = script.index('"$FIREWALL" >/dev/null 2>&1 || exit 1')
    ifdown_index = script.index("ifdown WireGuard")

    assert mode_index < firewall_index < ifdown_index


def test_render_off_matches_working_brume_behavior() -> None:
    script = OpenWrtLanVpnCommandRenderer().render_off()

    assert "ip rule del priority 1000 2>/dev/null || true" in script
    assert "ip route flush table 100 2>/dev/null || true" in script
    assert "ifdown WireGuard >/dev/null 2>&1 || true" in script
    assert (
        "if ip rule show | grep -q '1000:.*iif br-lan.*lookup 1000'; then" not in script
    )
    assert 'IP_RULES="$(ip rule show)"' in script
    assert "grep -Eq 'lookup 100([[:space:]]|$)'" in script
    assert "IP policy rules still reference VPN routing table 100" in script
    assert "read_vpn_routes || {" in script
    assert 'if [ -n "$TABLE_100_ROUTES" ]; then' in script
    assert "Routes remain in VPN routing table 100" in script
    assert 'echo "VPN LAN: OFF"' in script


def test_render_off_is_independent_of_maxvpn_api() -> None:
    script = OpenWrtLanVpnCommandRenderer().render_off()

    assert "127.0.0.1:8080" not in script
    assert "maxvpn-backend" not in script
    assert "/api/" not in script


def test_rendered_mode_scripts_have_valid_shell_syntax() -> None:
    import subprocess

    renderer = OpenWrtLanVpnCommandRenderer()
    scripts = {
        "vpn-on": renderer.render_on(),
        "vless-on": renderer.render_vless_on(),
        "wan-off": renderer.render_off(),
    }

    for name, script in scripts.items():
        result = subprocess.run(
            ["sh", "-n"], input=script, text=True, capture_output=True, check=False
        )
        assert result.returncode == 0, f"{name}: {result.stderr}"


def test_render_on_keeps_transition_guards_when_wireguard_start_fails(tmp_path) -> None:
    import os
    import subprocess

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "commands.log"

    logging_stub = """#!/bin/sh
printf '%s %s\\n' "$(basename "$0")" "$*" >> "$MAXVPN_TEST_LOG"
exit 0
"""
    for command in ("iptables", "ip6tables"):
        path = bin_dir / command
        path.write_text(logging_stub)
        path.chmod(0o755)

    ifstatus = bin_dir / "ifstatus"
    ifstatus.write_text("""#!/bin/sh
printf '%s\\n' '{"up": false}'
""")
    ifstatus.chmod(0o755)

    ifup = bin_dir / "ifup"
    ifup.write_text("""#!/bin/sh
printf 'ifup %s\\n' "$*" >> "$MAXVPN_TEST_LOG"
exit 43
""")
    ifup.chmod(0o755)

    firewall = tmp_path / "firewall.user"
    firewall.write_text("#!/bin/sh\nexit 0\n")
    firewall.chmod(0o755)
    hotplug = tmp_path / "hotplug"
    hotplug.write_text("#!/bin/sh\nexit 0\n")
    hotplug.chmod(0o755)
    runtime_mode = tmp_path / "runtime-mode"

    script = OpenWrtLanVpnCommandRenderer().render_on()
    script = (
        script.replace(
            "RUNTIME_MODE_FILE=/etc/maxvpn/runtime-mode",
            f"RUNTIME_MODE_FILE={runtime_mode}",
        )
        .replace(
            "HOTPLUG=/etc/hotplug.d/iface/99-lan-vpn",
            f"HOTPLUG={hotplug}",
        )
        .replace(
            "FIREWALL=/etc/maxvpn/firewall.user",
            f"FIREWALL={firewall}",
        )
    )
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["MAXVPN_TEST_LOG"] = str(log_path)

    result = subprocess.run(
        ["sh"], input=script, text=True, capture_output=True, check=False, env=env
    )
    log = log_path.read_text()

    assert result.returncode == 1
    assert runtime_mode.read_text().strip() == "vpn"
    assert "ifup WireGuard" in log
    assert "iptables -D forwarding_rule -j MAXVPN_MODE_TRANSITION_GUARD" not in log
    assert "ip6tables -D forwarding_rule -j MAXVPN6_MODE_GUARD" not in log


def test_mode_helpers_share_one_reentrant_runtime_lock() -> None:
    renderer = OpenWrtLanVpnCommandRenderer()
    scripts = {
        "vpn-on": renderer.render_on(),
        "vless-on": renderer.render_vless_on(),
        "wan-off": renderer.render_off(),
    }

    for name, script in scripts.items():
        assert "RUNTIME_LOCK_FILE=/tmp/maxvpn-runtime.lock" in script, name
        assert "flock -x 9" in script, name
        assert "export MAXVPN_RUNTIME_LOCK_HELD=1" in script, name
        assert "if ! ( : >&9 ) 2>/dev/null; then" in script, name

    for name, script in scripts.items():
        lock_index = script.index("flock -x 9")
        first_mode_mutation = script.index('> "$RUNTIME_MODE_FILE"')
        assert lock_index < first_mode_mutation, name


def test_vless_repair_checks_expected_mode_after_acquiring_runtime_lock() -> None:
    script = OpenWrtLanVpnCommandRenderer().render_vless_on()

    lock_index = script.index("flock -x 9")
    mode_read = script.index('PREVIOUS_MODE="$(cat "$RUNTIME_MODE_FILE"')
    expected_mode_check = script.index('"${MAXVPN_EXPECT_RUNTIME_MODE:-}" = "vless"')
    guard_install = script.index("ensure_transition_guards || {")

    assert lock_index < mode_read < expected_mode_check < guard_install
    assert "refusing stale repair" in script


def test_vless_rollback_wan_checks_route_reads_and_table_references() -> None:
    script = OpenWrtLanVpnCommandRenderer().render_vless_on()
    verify = script.split("verify_previous_mode() {", 1)[1].split(
        "rollback_previous_mode() {", 1
    )[0]
    wan_case = verify.split("wan)", 1)[1].split("vpn)", 1)[0]

    assert 'IP_RULES="$(ip rule show)" || return 1' in verify
    assert "read_vpn_routes || return 1" in verify
    assert "grep -Eq 'lookup 100([[:space:]]|$)'" in wan_case
    assert '[ -z "$TABLE_100_ROUTES" ] || return 1' in wan_case


def test_transition_guard_cleanup_checks_full_table_before_detaching() -> None:
    script = OpenWrtLanVpnCommandRenderer().render_vless_on()

    cleanup_start = script.index("remove_one_transition_guard() {")
    cleanup_end = script.index("\n}\n\nremove_transition_guards()", cleanup_start)
    cleanup = script[cleanup_start:cleanup_end]

    assert cleanup.index('RULES="$($FAMILY -S 2>/dev/null)"') < cleanup.index(
        'while "$FAMILY" -D forwarding_rule'
    )
    assert "Unable to inspect firewall rules while removing $CHAIN" in cleanup
    assert 'grep -F -x -e "-N $CHAIN"' in cleanup
    assert 'grep -F -e "-j $CHAIN" -e "-g $CHAIN"' in cleanup
    assert "has a non-standard firewall reference; refusing cleanup" in cleanup
    assert "still referenced by a firewall rule" in cleanup


def _install_vless_rollback_shell_stubs(
    tmp_path,
    *,
    dns_rule: str = "",
    fail_rule_inspect: bool = False,
    fail_second_firewall: bool = False,
    fail_guard_inspect: bool = False,
    seed_duplicate_guards: bool = False,
    seed_nonstandard_guard_reference: bool = False,
):
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state_dir = tmp_path / "iptables-state"
    state_dir.mkdir()
    log_path = tmp_path / "commands.log"
    runtime_mode = tmp_path / "runtime-mode"
    runtime_mode.write_text("wan\n")
    firewall_count = tmp_path / "firewall.count"

    iptables_stub = """#!/bin/sh
name=${0##*/}
log="$MAXVPN_TEST_LOG"
state="$MAXVPN_TEST_STATE_DIR/$name.rules"
[ -f "$state" ] || : > "$state"
echo "$name $*" >> "$log"
if [ "$1" = "-t" ]; then shift 2; fi
action=$1
shift || true
case "$action" in
    -S)
        if [ "$name" = "iptables" ] \
           && [ "${MAXVPN_TEST_FAIL_GUARD_INSPECT:-0}" = "1" ]; then
            exit 71
        fi
        if [ "$#" -eq 2 ]; then
            grep -F -e "-A $1 " "$state" | sed -n "$2 p"
        else
            cat "$state"
        fi
        exit 0
        ;;
    -N)
        chain=$1
        grep -F -x -q -e "-N $chain" "$state" || echo "-N $chain" >> "$state"
        exit 0
        ;;
    -A|-I)
        chain=$1
        shift
        if [ "$action" = "-I" ] \
           && [ "${1:-}" -eq "${1:-x}" ] 2>/dev/null; then
            shift
        fi
        echo "-A $chain $*" >> "$state"
        exit 0
        ;;
    -C|-D)
        chain=$1
        shift
        rule="-A $chain $*"
        if ! grep -F -x -q -e "$rule" "$state"; then exit 1; fi
        if [ "$action" = "-D" ]; then
            tmp="$state.tmp"
            awk -v rule="$rule" '
                BEGIN { removed=0 }
                $0 == rule && !removed { removed=1; next }
                { print }
            ' "$state" > "$tmp"
            mv "$tmp" "$state"
        fi
        exit 0
        ;;
    -F)
        chain=$1
        tmp="$state.tmp"
        awk -v prefix="-A $chain " 'index($0, prefix) != 1 { print }' "$state" > "$tmp"
        mv "$tmp" "$state"
        exit 0
        ;;
    -X)
        chain=$1
        if grep -F -q -e "-j $chain" -e "-g $chain" "$state"; then exit 1; fi
        tmp="$state.tmp"
        awk -v definition="-N $chain" '$0 != definition { print }' "$state" > "$tmp"
        mv "$tmp" "$state"
        exit 0
        ;;
esac
exit 0
"""
    for name in ("iptables", "ip6tables"):
        path = bin_dir / name
        path.write_text(iptables_stub, encoding="utf-8")
        path.chmod(0o755)

    if seed_duplicate_guards:
        duplicate_guard_rules = {
            "iptables": (
                "-N MAXVPN_MODE_TRANSITION_GUARD\n"
                "-A MAXVPN_MODE_TRANSITION_GUARD -i br-lan -o eth1 -j DROP\n"
                "-A forwarding_rule -j MAXVPN_MODE_TRANSITION_GUARD\n"
                "-A forwarding_rule -j MAXVPN_MODE_TRANSITION_GUARD\n"
            ),
            "ip6tables": (
                "-N MAXVPN6_MODE_GUARD\n"
                "-A MAXVPN6_MODE_GUARD -i br-lan -o eth1 -j DROP\n"
                "-A forwarding_rule -j MAXVPN6_MODE_GUARD\n"
                "-A forwarding_rule -j MAXVPN6_MODE_GUARD\n"
            ),
        }
        for name, rules in duplicate_guard_rules.items():
            (state_dir / f"{name}.rules").write_text(rules, encoding="utf-8")

    if seed_nonstandard_guard_reference:
        with (state_dir / "iptables.rules").open("a", encoding="utf-8") as state_file:
            state_file.write("-A custom_chain -j MAXVPN_MODE_TRANSITION_GUARD\n")

    ip_stub = """#!/bin/sh
case "$1:$2" in
    rule:show)
        [ "${MAXVPN_TEST_FAIL_RULE_INSPECT:-0}" != "1" ] || exit 72
        [ -z "$MAXVPN_TEST_DNS_RULE" ] || printf '%s\n' "$MAXVPN_TEST_DNS_RULE"
        ;;
    route:show)
        printf '%s\n' "$MAXVPN_TEST_ROUTES"
        ;;
    link:show)
        printf '%s\n' '7: maxvpn0: <POINTOPOINT,UP,LOWER_UP> mtu 9000'
        ;;
esac
exit 0
"""
    (bin_dir / "ip").write_text(ip_stub, encoding="utf-8")
    (bin_dir / "ip").chmod(0o755)

    for name, body in {
        "pidof": "#!/bin/sh\nexit 0\n",
        "ifstatus": "#!/bin/sh\nprintf '%s\\n' '{\"up\": false}'\n",
        "hotplug": "#!/bin/sh\nexit 0\n",
        "sing-box": "#!/bin/sh\nexit 0\n",
    }.items():
        path = bin_dir / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)

    firewall = tmp_path / "firewall.user"
    fail_second = "1" if fail_second_firewall else "0"
    firewall.write_text(
        f"""#!/bin/sh
count=0
[ -f "{firewall_count}" ] && count=$(cat "{firewall_count}")
count=$((count + 1))
printf '%s\\n' "$count" > "{firewall_count}"
mode=$(cat "{runtime_mode}")
printf 'firewall-%s-%s\\n' "$mode" "$count" >> "$MAXVPN_TEST_LOG"
if [ "$count" -eq 1 ]; then exit 0; fi
if [ "{fail_second}" = "1" ]; then exit 76; fi
iptables -N MAXVPN_LAN_FORWARD 2>/dev/null || true
iptables -A MAXVPN_LAN_FORWARD -i br-lan -o eth1 -j ACCEPT
iptables -I forwarding_rule 1 -j MAXVPN_LAN_FORWARD
ip6tables -N MAXVPN_LAN6_FORWARD 2>/dev/null || true
ip6tables -A MAXVPN_LAN6_FORWARD -i br-lan -o eth1 -j ACCEPT
ip6tables -I forwarding_rule 1 -j MAXVPN_LAN6_FORWARD
iptables -t nat -N MAXVPN_DIRECT_NAT 2>/dev/null || true
iptables -t nat -A MAXVPN_DIRECT_NAT -o eth1 -m mark --mark 0x64/0xff -j MASQUERADE
iptables -t nat -I POSTROUTING 1 -j MAXVPN_DIRECT_NAT
exit 0
""",
        encoding="utf-8",
    )
    firewall.chmod(0o755)

    hotplug = bin_dir / "hotplug-script"
    hotplug.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hotplug.chmod(0o755)
    sing_box_config = tmp_path / "sing-box.json"
    sing_box_config.write_text("{}\n", encoding="utf-8")

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["MAXVPN_TEST_STATE_DIR"] = str(state_dir)
    env["MAXVPN_TEST_LOG"] = str(log_path)
    if dns_rule:
        env["MAXVPN_TEST_DNS_RULE"] = dns_rule
    if fail_guard_inspect:
        env["MAXVPN_TEST_FAIL_GUARD_INSPECT"] = "1"
    if fail_rule_inspect:
        env["MAXVPN_TEST_FAIL_RULE_INSPECT"] = "1"

    script = OpenWrtLanVpnCommandRenderer().render_vless_on()
    script = (
        script.replace(
            "RUNTIME_MODE_FILE=/etc/maxvpn/runtime-mode",
            f"RUNTIME_MODE_FILE={runtime_mode}",
        )
        .replace("HOTPLUG=/etc/hotplug.d/iface/99-lan-vpn", f"HOTPLUG={hotplug}")
        .replace("FIREWALL=/etc/maxvpn/firewall.user", f"FIREWALL={firewall}")
        .replace("SING_BOX=/usr/bin/sing-box", f"SING_BOX={bin_dir / 'sing-box'}")
        .replace(
            "SING_BOX_CONFIG=/etc/maxvpn/sing-box-vless.json",
            f"SING_BOX_CONFIG={sing_box_config}",
        )
        .replace(
            "RUNTIME_LOCK_FILE=/tmp/maxvpn-runtime.lock",
            f"RUNTIME_LOCK_FILE={tmp_path / 'runtime.lock'}",
        )
    )
    return script, env, runtime_mode, state_dir, log_path


def _run_vless_rollback_case(tmp_path, **kwargs):
    import subprocess

    script, env, runtime_mode, state_dir, log_path = (
        _install_vless_rollback_shell_stubs(tmp_path, **kwargs)
    )
    result = subprocess.run(
        ["sh"], input=script, text=True, capture_output=True, check=False, env=env
    )
    return result, runtime_mode, state_dir, log_path


def test_vless_repair_refuses_to_switch_wan_back_to_vless(tmp_path) -> None:
    import subprocess

    script, env, runtime_mode, state_dir, _ = _install_vless_rollback_shell_stubs(
        tmp_path
    )
    env["MAXVPN_EXPECT_RUNTIME_MODE"] = "vless"
    result = subprocess.run(
        ["sh"], input=script, text=True, capture_output=True, check=False, env=env
    )

    assert result.returncode == 2
    assert runtime_mode.read_text().strip() == "wan"
    assert "refusing stale repair" in result.stderr
    rules_path = state_dir / "iptables.rules"
    rules = rules_path.read_text() if rules_path.exists() else ""
    assert "MAXVPN_MODE_TRANSITION_GUARD" not in rules


def test_vless_rollback_dynamically_restores_wan_and_removes_duplicate_guards(
    tmp_path,
) -> None:
    result, runtime_mode, state_dir, log_path = _run_vless_rollback_case(
        tmp_path, seed_duplicate_guards=True
    )

    # The deliberately absent VLESS chain triggers rollback.
    assert result.returncode == 1
    assert runtime_mode.read_text().strip() == "wan"
    v4 = (state_dir / "iptables.rules").read_text()
    v6 = (state_dir / "ip6tables.rules").read_text()
    assert "-N MAXVPN_MODE_TRANSITION_GUARD" not in v4
    assert "-j MAXVPN_MODE_TRANSITION_GUARD" not in v4
    assert "-N MAXVPN6_MODE_GUARD" not in v6
    assert "-j MAXVPN6_MODE_GUARD" not in v6
    log = log_path.read_text()
    assert log.count("iptables -D forwarding_rule -j MAXVPN_MODE_TRANSITION_GUARD") == 3
    assert log.count("ip6tables -D forwarding_rule -j MAXVPN6_MODE_GUARD") == 3
    assert "-A MAXVPN_LAN_FORWARD -i br-lan -o eth1 -j ACCEPT" in v4


def test_vless_rollback_keeps_guard_attached_for_nonstandard_reference(
    tmp_path,
) -> None:
    result, runtime_mode, state_dir, _ = _run_vless_rollback_case(
        tmp_path, seed_nonstandard_guard_reference=True
    )

    assert result.returncode == 1
    assert runtime_mode.read_text().strip() == "wan"
    v4 = (state_dir / "iptables.rules").read_text()
    assert "-A forwarding_rule -j MAXVPN_MODE_TRANSITION_GUARD" in v4
    assert "-A custom_chain -j MAXVPN_MODE_TRANSITION_GUARD" in v4
    assert "non-standard firewall reference; refusing cleanup" in result.stderr
    assert "rollback incomplete, transition guards retained" in result.stderr


def test_vless_rollback_keeps_guards_when_previous_firewall_restore_fails(
    tmp_path,
) -> None:
    result, runtime_mode, state_dir, _ = _run_vless_rollback_case(
        tmp_path, fail_second_firewall=True
    )

    assert result.returncode == 1
    assert runtime_mode.read_text().strip() == "wan"
    v4 = (state_dir / "iptables.rules").read_text()
    v6 = (state_dir / "ip6tables.rules").read_text()
    assert "-A forwarding_rule -j MAXVPN_MODE_TRANSITION_GUARD" in v4
    assert "-A MAXVPN_MODE_TRANSITION_GUARD -i br-lan -o eth1 -j DROP" in v4
    assert "-A forwarding_rule -j MAXVPN6_MODE_GUARD" in v6
    assert "-A MAXVPN6_MODE_GUARD -i br-lan -o eth1 -j DROP" in v6


def test_vless_rollback_rejects_stale_wan_dns_rules_and_keeps_guards(tmp_path) -> None:
    result, runtime_mode, state_dir, _ = _run_vless_rollback_case(
        tmp_path, dns_rule="200: from all to 1.1.1.1 lookup 100"
    )

    assert result.returncode == 1
    assert runtime_mode.read_text().strip() == "wan"
    v4 = (state_dir / "iptables.rules").read_text()
    assert "-A forwarding_rule -j MAXVPN_MODE_TRANSITION_GUARD" in v4


def test_vless_rollback_keeps_both_guards_when_policy_rule_inspection_fails(
    tmp_path,
) -> None:
    result, _, state_dir, _ = _run_vless_rollback_case(tmp_path, fail_rule_inspect=True)
    v4 = (state_dir / "iptables.rules").read_text()
    v6 = (state_dir / "ip6tables.rules").read_text()

    assert result.returncode == 1
    assert "rollback incomplete, transition guards retained" in result.stderr
    assert "-A forwarding_rule -j MAXVPN_MODE_TRANSITION_GUARD" in v4
    assert "-A forwarding_rule -j MAXVPN6_MODE_GUARD" in v6


def test_vless_rollback_keeps_guard_when_full_firewall_inspection_fails(
    tmp_path,
) -> None:
    result, runtime_mode, state_dir, _ = _run_vless_rollback_case(
        tmp_path, fail_guard_inspect=True
    )

    assert result.returncode == 1
    assert runtime_mode.read_text().strip() == "wan"
    v4 = (state_dir / "iptables.rules").read_text()
    assert "-A forwarding_rule -j MAXVPN_MODE_TRANSITION_GUARD" in v4


def test_runtime_mode_helpers_serialize_competing_switches_with_inherited_lock(
    tmp_path,
) -> None:
    import os
    import subprocess
    import time

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "runtime.log"
    runtime_mode = tmp_path / "runtime-mode"
    runtime_mode.write_text("wan\n")
    lock_path = tmp_path / "runtime.lock"

    for name in ("iptables", "ip6tables"):
        path = bin_dir / name
        path.write_text(
            f'#!/bin/sh\necho {name} "$*" >> "{log_path}"\nexit 0\n',
            encoding="utf-8",
        )
        path.chmod(0o755)
    ip = bin_dir / "ip"
    ip.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    ip.chmod(0o755)
    ifstatus = bin_dir / "ifstatus"
    ifstatus.write_text(
        "#!/bin/sh\nprintf '%s\\n' '{\"up\": false}'\n",
        encoding="utf-8",
    )
    ifstatus.chmod(0o755)
    ifdown = bin_dir / "ifdown"
    ifdown.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    ifdown.chmod(0o755)

    ifup = bin_dir / "ifup"
    ifup.write_text(
        f"""#!/bin/sh
echo ifup-start >> "{log_path}"
sleep 0.5
echo ifup-end >> "{log_path}"
exit 43
""",
        encoding="utf-8",
    )
    ifup.chmod(0o755)

    firewall = tmp_path / "firewall.user"
    firewall.write_text(
        f"""#!/bin/sh
if [ "${{MAXVPN_RUNTIME_LOCK_HELD:-0}}" != "1" ] || ! ( : >&9 ) 2>/dev/null; then
  echo nested-lock-missing >> "{log_path}"
  exit 98
fi
mode=$(cat "{runtime_mode}")
echo firewall-$mode >> "{log_path}"
exit 0
""",
        encoding="utf-8",
    )
    firewall.chmod(0o755)
    hotplug = tmp_path / "hotplug"
    hotplug.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hotplug.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    renderer = OpenWrtLanVpnCommandRenderer()
    on_script = (
        renderer.render_on()
        .replace(
            "RUNTIME_MODE_FILE=/etc/maxvpn/runtime-mode",
            f"RUNTIME_MODE_FILE={runtime_mode}",
        )
        .replace("HOTPLUG=/etc/hotplug.d/iface/99-lan-vpn", f"HOTPLUG={hotplug}")
        .replace("FIREWALL=/etc/maxvpn/firewall.user", f"FIREWALL={firewall}")
        .replace(
            "RUNTIME_LOCK_FILE=/tmp/maxvpn-runtime.lock",
            f"RUNTIME_LOCK_FILE={lock_path}",
        )
    )
    off_script = (
        renderer.render_off()
        .replace(
            "RUNTIME_MODE_FILE=/etc/maxvpn/runtime-mode",
            f"RUNTIME_MODE_FILE={runtime_mode}",
        )
        .replace("FIREWALL=/etc/maxvpn/firewall.user", f"FIREWALL={firewall}")
        .replace(
            "RUNTIME_LOCK_FILE=/tmp/maxvpn-runtime.lock",
            f"RUNTIME_LOCK_FILE={lock_path}",
        )
    )

    first = subprocess.Popen(
        ["sh"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert first.stdin is not None
    first.stdin.write(on_script)
    first.stdin.close()

    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if log_path.exists() and "ifup-start" in log_path.read_text():
            break
        time.sleep(0.02)
    else:
        first.kill()
        first.stdin = None
        first_out, first_err = first.communicate()
        diagnostic_log = log_path.read_text() if log_path.exists() else "<empty>"
        raise AssertionError(
            "first helper never reached delayed ifup step; "
            f"exit={first.returncode}; stdout={first_out!r}; "
            f"stderr={first_err!r}; log={diagnostic_log!r}"
        )

    second = subprocess.Popen(
        ["sh"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert second.stdin is not None
    second.stdin.write(off_script)
    second.stdin.close()
    time.sleep(0.1)

    assert runtime_mode.read_text().strip() == "vpn"
    first.wait(timeout=3)
    second.wait(timeout=3)
    log = log_path.read_text()

    assert first.returncode == 1
    assert second.returncode == 0
    assert runtime_mode.read_text().strip() == "wan"
    assert log.index("ifup-end") < log.index("firewall-wan")
    assert "nested-lock-missing" not in log

    # Re-running the WAN helper must be safe after a completed transition.
    repeated = subprocess.run(
        ["sh"], input=off_script, text=True, capture_output=True, check=False, env=env
    )
    assert repeated.returncode == 0, repeated.stderr
    assert runtime_mode.read_text().strip() == "wan"
    assert log_path.read_text().count("firewall-wan") == 4


def _run_render_off_shell_case(
    tmp_path,
    *,
    firewall_fail_at=0,
    ifdown_fails=False,
    rule_output="",
    route_output="",
    route_error="",
    wg_inventory=None,
):
    import os
    import subprocess

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    log_path = tmp_path / "commands.log"
    runtime_mode = tmp_path / "runtime-mode"
    runtime_mode.write_text("vless\n")
    wg_status = tmp_path / "wg-status.json"
    wg_status.write_text('{"up": true}\n')
    rules_file = tmp_path / "rules.txt"
    rules_file.write_text(rule_output)
    routes_file = tmp_path / "routes.txt"
    routes_file.write_text(route_output)
    firewall_count = tmp_path / "firewall-count"

    iptables_stub = r"""#!/bin/sh
FAMILY=$(basename "$0")
case "$FAMILY" in
    iptables) GUARD=MAXVPN_MODE_TRANSITION_GUARD ;;
    ip6tables) GUARD=MAXVPN6_MODE_GUARD ;;
    *) exit 90 ;;
esac
STATE="$MAXVPN_TEST_STATE/$FAMILY"
mkdir -p "$STATE"
printf '%s %s\n' "$FAMILY" "$*" >> "$MAXVPN_TEST_LOG"
case "$1" in
    -N)
        [ "$2" = "$GUARD" ] && : > "$STATE/chain"
        exit 0
        ;;
    -A)
        [ "$2" = "$GUARD" ] && : > "$STATE/rule"
        exit 0
        ;;
    -C)
        if [ "$2" = "$GUARD" ]; then
            [ -f "$STATE/rule" ]
            exit $?
        fi
        case "$*" in
            *"forwarding_rule -j $GUARD"*)
                [ -f "$STATE/attached" ]
                exit $?
                ;;
        esac
        # The test firewall policy's normal verification checks succeed.
        exit 0
        ;;
    -I)
        case "$*" in
            *"forwarding_rule 1 -j $GUARD"*) : > "$STATE/attached" ;;
        esac
        exit 0
        ;;
    -S)
        [ -f "$STATE/chain" ] && echo "-N $GUARD"
        [ -f "$STATE/attached" ] && echo "-A forwarding_rule -j $GUARD"
        exit 0
        ;;
    -D)
        case "$*" in
            *"forwarding_rule -j $GUARD"*)
                if [ -f "$STATE/attached" ]; then
                    rm -f "$STATE/attached"
                    exit 0
                fi
                exit 1
                ;;
        esac
        exit 1
        ;;
    -F)
        [ "$2" = "$GUARD" ] && rm -f "$STATE/rule"
        exit 0
        ;;
    -X)
        [ "$2" = "$GUARD" ] && rm -f "$STATE/chain"
        exit 0
        ;;
esac
exit 0
"""
    for name in ("iptables", "ip6tables"):
        path = bin_dir / name
        path.write_text(iptables_stub)
        path.chmod(0o755)

    ip_stub = r"""#!/bin/sh
printf 'ip %s\n' "$*" >> "$MAXVPN_TEST_LOG"
case "$*" in
    "rule show") cat "$MAXVPN_TEST_RULES_FILE" ;;
    "route show table 100")
        if [ -n "$MAXVPN_TEST_ROUTE_ERROR" ]; then
            printf '%s\n' "$MAXVPN_TEST_ROUTE_ERROR" >&2
            exit 2
        fi
        cat "$MAXVPN_TEST_ROUTES_FILE"
        ;;
    *) exit 0 ;;
esac
"""
    ip = bin_dir / "ip"
    ip.write_text(ip_stub)
    ip.chmod(0o755)

    ifstatus = bin_dir / "ifstatus"
    ifstatus.write_text('#!/bin/sh\ncat "$MAXVPN_TEST_WG_STATUS_FILE"\n')
    ifstatus.chmod(0o755)

    ifdown = bin_dir / "ifdown"
    ifdown.write_text("""#!/bin/sh
echo "ifdown $*" >> "$MAXVPN_TEST_LOG"
if [ "${MAXVPN_TEST_IFDOWN_FAIL:-0}" = "1" ]; then exit 1; fi
printf '%s\\n' '{"up": false}' > "$MAXVPN_TEST_WG_STATUS_FILE"
exit 0
""")
    ifdown.chmod(0o755)

    firewall = tmp_path / "firewall.user"
    firewall.write_text("""#!/bin/sh
count=0
[ ! -f "$MAXVPN_TEST_FIREWALL_COUNT" ] || count=$(cat "$MAXVPN_TEST_FIREWALL_COUNT")
count=$((count + 1))
printf '%s\\n' "$count" > "$MAXVPN_TEST_FIREWALL_COUNT"
echo "firewall-$count" >> "$MAXVPN_TEST_LOG"
if [ "$count" -eq "$MAXVPN_TEST_FIREWALL_FAIL_AT" ]; then exit 1; fi
exit 0
""")
    firewall.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env.update(
        {
            "MAXVPN_TEST_LOG": str(log_path),
            "MAXVPN_TEST_STATE": str(state_dir),
            "MAXVPN_TEST_WG_STATUS_FILE": str(wg_status),
            "MAXVPN_TEST_RULES_FILE": str(rules_file),
            "MAXVPN_TEST_ROUTES_FILE": str(routes_file),
            "MAXVPN_TEST_ROUTE_ERROR": route_error,
            "MAXVPN_TEST_FIREWALL_COUNT": str(firewall_count),
            "MAXVPN_TEST_FIREWALL_FAIL_AT": str(firewall_fail_at),
            "MAXVPN_TEST_IFDOWN_FAIL": "1" if ifdown_fails else "0",
        }
    )

    if wg_inventory is not None:
        ifstatus.write_text("#!/bin/sh\nexit 1\n")
        for command in ("uci", "ubus", "ip"):
            output, status = wg_inventory.get(command, ("", 0))
            inventory = tmp_path / f"{command}-inventory"
            inventory.write_text(output)
            stub = bin_dir / command
            if command == "ip":
                prefix = (
                    '#!/bin/sh\nif [ "$*" = "-o link show" ]; then\n'
                    f'cat "{inventory}"\nexit {status}\nfi\n'
                )
                stub.write_text(prefix + ip_stub.removeprefix("#!/bin/sh\n"))
            else:
                stub.write_text(f'#!/bin/sh\ncat "{inventory}"\nexit {status}\n')
            stub.chmod(0o755)

    script = OpenWrtLanVpnCommandRenderer().render_off()
    script = (
        script.replace(
            "RUNTIME_MODE_FILE=/etc/maxvpn/runtime-mode",
            f"RUNTIME_MODE_FILE={runtime_mode}",
        )
        .replace(
            "FIREWALL=/etc/maxvpn/firewall.user",
            f"FIREWALL={firewall}",
        )
        .replace(
            "RUNTIME_LOCK_FILE=/tmp/maxvpn-runtime.lock",
            f"RUNTIME_LOCK_FILE={tmp_path / 'runtime.lock'}",
        )
    )
    result = subprocess.run(
        ["sh"], input=script, text=True, capture_output=True, check=False, env=env
    )
    log = log_path.read_text() if log_path.exists() else ""
    return result, runtime_mode, state_dir, log


def test_render_off_installs_guards_before_mutating_runtime_mode() -> None:
    script = OpenWrtLanVpnCommandRenderer().render_off()

    lock = script.index("flock -x 9")
    guard_definitions = script.index("ensure_transition_guards() {")
    guard_install = script.index("ensure_transition_guards || {")
    mode_change = script.index("printf '%s\\n' wan")

    assert lock < guard_definitions < guard_install < mode_change


@pytest.mark.parametrize("firewall_fail_at", [1, 2])
def test_render_off_keeps_transition_guards_when_firewall_apply_fails(
    tmp_path, firewall_fail_at
) -> None:
    result, runtime_mode, state_dir, log = _run_render_off_shell_case(
        tmp_path, firewall_fail_at=firewall_fail_at
    )

    assert result.returncode == 1
    assert runtime_mode.read_text().strip() == "wan"
    assert (state_dir / "iptables" / "attached").exists()
    assert (state_dir / "ip6tables" / "attached").exists()
    assert "iptables -D forwarding_rule -j MAXVPN_MODE_TRANSITION_GUARD" not in log
    assert "ip6tables -D forwarding_rule -j MAXVPN6_MODE_GUARD" not in log


def test_render_off_keeps_guards_when_wireguard_remains_up_after_ifdown(
    tmp_path,
) -> None:
    result, _, state_dir, log = _run_render_off_shell_case(tmp_path, ifdown_fails=True)

    assert result.returncode == 1
    assert "WireGuard remains up after ifdown" in result.stderr
    assert "ifdown WireGuard" in log
    assert (state_dir / "iptables" / "attached").exists()
    assert (state_dir / "ip6tables" / "attached").exists()
    assert "firewall-2" not in log


@pytest.mark.parametrize(
    ("rule_output", "route_output", "expected_error"),
    [
        (
            "200: from all to 1.1.1.1 lookup 100\n",
            "",
            "IP policy rules still reference VPN routing table 100",
        ),
        (
            "",
            "default dev WireGuard scope link\n",
            "Routes remain in VPN routing table 100",
        ),
        (
            "",
            "default dev maxvpn0 scope link\n",
            "Routes remain in VPN routing table 100",
        ),
    ],
)
def test_render_off_keeps_guards_when_stale_vpn_policy_remains(
    tmp_path, rule_output, route_output, expected_error
) -> None:
    result, _, state_dir, log = _run_render_off_shell_case(
        tmp_path, rule_output=rule_output, route_output=route_output
    )

    assert result.returncode == 1
    assert expected_error in result.stderr
    assert (state_dir / "iptables" / "attached").exists()
    assert (state_dir / "ip6tables" / "attached").exists()
    assert "iptables -D forwarding_rule -j MAXVPN_MODE_TRANSITION_GUARD" not in log
    assert "ip6tables -D forwarding_rule -j MAXVPN6_MODE_GUARD" not in log


@pytest.mark.parametrize(
    ("route_error", "expected_status"),
    [
        ("Error: ipv4: FIB table does not exist.\nDump terminated", 0),
        ("RTNETLINK answers: Permission denied", 1),
    ],
)
def test_render_off_distinguishes_missing_table_from_route_read_failure(
    tmp_path, route_error, expected_status
) -> None:
    result, _, state_dir, _ = _run_render_off_shell_case(
        tmp_path, route_error=route_error
    )

    assert result.returncode == expected_status, result.stderr
    for family in ("iptables", "ip6tables"):
        assert (state_dir / family / "attached").exists() == (expected_status != 0)


def test_vless_activation_waits_for_atomic_stop(tmp_path, monkeypatch) -> None:
    import os
    import subprocess
    import time

    renderer = OpenWrtLanVpnCommandRenderer()
    mode = tmp_path / "runtime-mode"
    mode.write_text("vless\n")
    lock = tmp_path / "runtime.lock"
    (tmp_path / "running").touch()
    release_stop = tmp_path / "finish-stop"

    def stub(name, body):
        script = tmp_path / name
        script.write_text("#!/bin/sh\nset -eu\n" + body)
        script.chmod(0o755)
        return script

    switch_wan = stub(
        "vpn-lan-off",
        """
test "$MAXVPN_RUNTIME_LOCK_HELD" = 1
: >&9
printf '%s\\n' wan > "$STATE/runtime-mode"
""",
    )
    service = stub(
        "maxvpn-sing-box",
        """
case "$1" in
    running) test -f "$STATE/running" ;;
    stop)
        test "$(cat "$STATE/runtime-mode")" = wan
        touch "$STATE/stopping"
        until [ -f "$STATE/finish-stop" ]; do sleep 0.05; done
        rm "$STATE/running"
        ;;
    disable) touch "$STATE/disabled" ;;
esac
""",
    )
    sing_box = stub("sing-box", "exit 0\n")
    # Simulate the lingering process and TUN after procd has stopped the service.
    stub("pidof", "exit 0\n")
    stub("ip", 'printf "%s\\n" "maxvpn0 state UP"\n')
    stub("iptables", "exit 77\n")
    stub("ip6tables", "exit 77\n")
    firewall = stub("firewall", "exit 77\n")
    hotplug = stub("hotplug", "exit 77\n")

    monkeypatch.setenv("STATE", str(tmp_path))
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    monkeypatch.delenv("MAXVPN_RUNTIME_LOCK_HELD", raising=False)
    paths = {
        "/tmp/maxvpn-runtime.lock": lock,
        renderer.RUNTIME_MODE_FILE: mode,
        renderer.VPN_LAN_OFF: switch_wan,
        renderer.VLESS_SERVICE: service,
        "/usr/bin/sing-box": sing_box,
        renderer.FIREWALL: firewall,
        renderer.HOTPLUG: hotplug,
    }

    def script_file(name, content):
        for original, replacement in paths.items():
            content = content.replace(original, str(replacement))
        path = tmp_path / name
        path.write_text(content)
        return path

    stop_path = script_file("stop-script", renderer.render_vless_stop())
    activate_path = script_file("activate-script", renderer.render_vless_on())

    with subprocess.Popen(
        ["sh", str(stop_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as stop:
        try:
            deadline = time.monotonic() + 5
            while not (tmp_path / "stopping").exists() and time.monotonic() < deadline:
                if stop.poll() is not None:
                    break
                time.sleep(0.01)
            assert (tmp_path / "stopping").exists()
            with subprocess.Popen(
                ["sh", str(activate_path)], text=True, stderr=subprocess.PIPE
            ) as activate:
                try:
                    with pytest.raises(subprocess.TimeoutExpired):
                        activate.wait(timeout=0.2)
                finally:
                    release_stop.touch()

                _, activation_error = activate.communicate(timeout=5)
                assert activate.returncode == 1
                assert "sing-box service is not running" in activation_error
        finally:
            release_stop.touch()

        previous_mode, stop_error = stop.communicate(timeout=5)
        assert stop.returncode == 0, stop_error

    assert previous_mode.strip() == "vless"
    assert mode.read_text().strip() == "wan"
    assert (tmp_path / "disabled").is_file()


@pytest.mark.parametrize(
    "inventory",
    [
        {},
        {
            "uci": ("network.lan=interface\n", 0),
            "ubus": ("network.interface.lan\n", 0),
            "ip": ("1: lo: <UP>\n", 0),
        },
    ],
)
def test_wan_switch_accepts_verified_wireguard_absence(tmp_path, inventory):
    result, mode, state, log = _run_render_off_shell_case(
        tmp_path, wg_inventory=inventory
    )
    assert result.returncode == 0, result.stderr
    assert mode.read_text().strip() == "wan"
    assert "WireGuard absent" in result.stdout
    assert "ifdown WireGuard" not in log
    for family in ("iptables", "ip6tables"):
        assert not (state / family / "attached").exists()


@pytest.mark.parametrize(
    "command,output,status",
    [
        ("uci", "network.WireGuard=interface\n", 0),
        ("ubus", "network.interface.WireGuard\n", 0),
        ("ip", "8: WireGuard: <UP>\n", 0),
        ("ip", "8: WireGuard@eth1: <UP>\n", 0),
        ("uci", "", 1),
        ("ubus", "", 1),
        ("ip", "", 1),
    ],
)
def test_wan_switch_retains_guards_for_unknown_wireguard_state(
    tmp_path, command, output, status
):
    result, _, state, log = _run_render_off_shell_case(
        tmp_path, wg_inventory={command: (output, status)}
    )
    assert result.returncode != 0
    assert "transition guards retained" in result.stderr
    assert "VPN LAN: OFF" not in result.stdout
    assert "ifdown WireGuard" not in log
    for family in ("iptables", "ip6tables"):
        assert (state / family / "attached").exists()
