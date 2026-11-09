"""Isolated runtime tests for the generated VLESS watchdog.

These tests run the actual generated POSIX shell script against fake commands in a
temporary directory. They never connect to or change a router.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from backend.infrastructure.openwrt.openwrt_lan_vpn_command_renderer import (
    OpenWrtLanVpnCommandRenderer,
)

IP_STUB = r"""#!/bin/sh
STATE="$MOCK_STATE"
case "$1:$2:$3" in
  link:show:maxvpn0)
    if [ -f "$STATE/tun-up" ]; then
      echo 'maxvpn0: <POINTOPOINT,MULTICAST,NOARP,UP,LOWER_UP>'
      exit 0
    fi
    echo "Device \"maxvpn0\" does not exist." >&2
    exit 1
    ;;
  rule:show:*)
    if [ -f "$STATE/policy-up" ]; then
      cat <<'RULES'
200: from all to 1.1.1.1 lookup 100
200: from all to 8.8.8.8 lookup 100
200: from all to 9.9.9.9 lookup 100
1000: from all iif br-lan lookup 100
RULES
    fi
    exit 0
    ;;
  route:show:table)
    if [ -f "$STATE/policy-up" ] && [ "$4" = "100" ]; then
      echo 'default dev maxvpn0 scope link'
    fi
    exit 0
    ;;
esac
# Unknown read-only ip probes fail closed in the test double.
exit 1
"""


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _build_sandbox(
    tmp_path: Path,
    *,
    scenario: str,
    mode: str = "vless",
    process_up: bool = False,
    tun_up: bool = False,
    policy_up: bool = False,
    invalid_config: bool = False,
    missing_ipv4_jump: bool = False,
    missing_ipv6_jump: bool = False,
    fail_policy_repair: bool = False,
) -> tuple[Path, Path, Path]:
    bindir = tmp_path / "bin"
    state = tmp_path / "state"
    bindir.mkdir()
    state.mkdir()
    log = tmp_path / "events.log"
    log.write_text("", encoding="utf-8")

    mode_file = state / "runtime-mode"
    mode_file.write_text(mode + "\n", encoding="utf-8")
    config = state / "sing-box.json"
    config.write_text("invalid" if invalid_config else "valid", encoding="utf-8")

    for flag, enabled in (
        ("process-up", process_up),
        ("tun-up", tun_up),
        ("policy-up", policy_up),
    ):
        if enabled:
            (state / flag).touch()
    if policy_up and not missing_ipv4_jump:
        (state / "ipv4-jump-up").touch()
    if policy_up and not missing_ipv6_jump:
        (state / "ipv6-jump-up").touch()
    if fail_policy_repair:
        (state / "fail-policy-repair").touch()

    _write_executable(bindir / "ip", IP_STUB)
    _write_executable(
        bindir / "pidof",
        (
            "#!/bin/sh\n"
            '[ -f "$MOCK_STATE/process-up" ] && { echo 4242; exit 0; }\n'
            "exit 1\n"
        ),
    )
    _write_executable(
        bindir / "sing-box",
        '#!/bin/sh\n[ "$1" = "check" ] || exit 1\n'
        '[ -r "$MOCK_CONFIG" ] || exit 1\n'
        'grep -q "^invalid$" "$MOCK_CONFIG" && exit 1\nexit 0\n',
    )
    _write_executable(
        bindir / "iptables",
        "#!/bin/sh\n"
        'if [ "$1" = "-C" ]; then\n'
        '  case "$*" in\n'
        '    *"forwarding_rule -j MAXVPN_LAN_FORWARD"*) '
        '[ -f "$MOCK_STATE/ipv4-jump-up" ] && exit 0; exit 1 ;;\n'
        "  esac\n"
        '  [ -f "$MOCK_STATE/policy-up" ] && exit 0\n'
        "  exit 1\n"
        "fi\n"
        'printf "firewall_mutation iptables %s\\n" "$*" >> "$MOCK_LOG"\n'
        "exit 1\n",
    )
    _write_executable(
        bindir / "ip6tables",
        "#!/bin/sh\n"
        'if [ "$1" = "-C" ]; then\n'
        '  case "$*" in\n'
        '    *"forwarding_rule -j MAXVPN_LAN6_FORWARD"*) '
        '[ -f "$MOCK_STATE/ipv6-jump-up" ] && exit 0; exit 1 ;;\n'
        "  esac\n"
        '  [ -f "$MOCK_STATE/policy-up" ] && exit 0\n'
        "  exit 1\n"
        "fi\n"
        'printf "firewall_mutation ip6tables %s\\n" "$*" >> "$MOCK_LOG"\n'
        "exit 1\n",
    )
    _write_executable(
        bindir / "logger",
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$MOCK_LOG"\nexit 0\n',
    )
    _write_executable(bindir / "sleep", "#!/bin/sh\nexit 0\n")
    _write_executable(
        bindir / "vpn-lan-vless-on",
        '#!/bin/sh\nprintf "route_restore\\n" >> "$MOCK_LOG"\n'
        '[ "$(cat "$MOCK_MODE_FILE")" = "vless" ] || exit 1\n'
        '[ -f "$MOCK_STATE/fail-policy-repair" ] && exit 1\n'
        'touch "$MOCK_STATE/policy-up" '
        '"$MOCK_STATE/ipv4-jump-up" "$MOCK_STATE/ipv6-jump-up"\n'
        "exit 0\n",
    )

    init_body = [
        "#!/bin/sh",
        'printf "service_action=%s\\n" "$1" >> "$MOCK_LOG"',
        '[ "$1" = "start" ] || [ "$1" = "restart" ] || exit 2',
        f'case "{scenario}" in',
        '  recovery) touch "$MOCK_STATE/process-up" "$MOCK_STATE/tun-up" ;;',
        "  service-action-fails) exit 1 ;;",
        '  timeout-no-tun) touch "$MOCK_STATE/process-up" ;;',
        '  mode-switch) printf "wan\\n" > "$MOCK_MODE_FILE" ;;',
        "  *) exit 3 ;;",
        "esac",
        "exit 0",
    ]
    _write_executable(bindir / "maxvpn-sing-box", "\n".join(init_body) + "\n")

    # Render the real implementation, then redirect only its absolute paths and
    # inject a finite loop limit so the long-running watchdog exits in the test.
    script = OpenWrtLanVpnCommandRenderer().render_vless_watchdog()
    replacements = {
        "RUNTIME_MODE_FILE=/etc/maxvpn/runtime-mode": f"RUNTIME_MODE_FILE={mode_file}",
        "VLESS_ON=/usr/bin/vpn-lan-vless-on": f"VLESS_ON={bindir / 'vpn-lan-vless-on'}",
        "SING_BOX=/usr/bin/sing-box": f"SING_BOX={bindir / 'sing-box'}",
        "SING_BOX_CONFIG=/etc/maxvpn/sing-box-vless.json": f"SING_BOX_CONFIG={config}",
        "SING_BOX_INIT=/etc/init.d/maxvpn-sing-box": (
            f"SING_BOX_INIT={bindir / 'maxvpn-sing-box'}"
        ),
    }
    for old, new in replacements.items():
        assert old in script, f"Expected template assignment not found: {old}"
        script = script.replace(old, new, 1)

    loop_marker = 'while :; do\n    if [ "$restart_cooldown" -gt 0 ]; then'
    loop_injection = (
        "test_loop_count=0\n"
        "while :; do\n"
        "    test_loop_count=$((test_loop_count + 1))\n"
        '    [ "$test_loop_count" -le 5 ] || break\n'
        '    if [ "$restart_cooldown" -gt 0 ]; then'
    )
    assert loop_marker in script
    script = script.replace(loop_marker, loop_injection, 1)

    watchdog = tmp_path / "watchdog.sh"
    _write_executable(watchdog, script)
    return watchdog, state, log


def _run_watchdog(tmp_path: Path, **kwargs: object) -> tuple[str, str, int]:
    watchdog, state, log = _build_sandbox(tmp_path, **kwargs)
    mode_file = state / "runtime-mode"
    config = state / "sing-box.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{tmp_path / 'bin'}:{env.get('PATH', '/usr/bin:/bin')}",
            "MOCK_STATE": str(state),
            "MOCK_LOG": str(log),
            "MOCK_MODE_FILE": str(mode_file),
            "MOCK_CONFIG": str(config),
        }
    )
    result = subprocess.run(
        ["/bin/sh", str(watchdog)],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=False,
    )
    event_log = log.read_text(encoding="utf-8")
    assert "firewall_mutation" not in event_log, event_log
    return event_log, result.stderr, result.returncode


def test_recovers_when_tun_is_missing_and_restores_routes(tmp_path: Path) -> None:
    log, stderr, rc = _run_watchdog(
        tmp_path, scenario="recovery", process_up=True, tun_up=False, policy_up=False
    )
    assert rc == 0, stderr
    assert log.splitlines().count("service_action=restart") == 1
    assert "attempting restart of maxvpn-sing-box" in log
    assert log.count("route_restore") == 1
    assert "sing-box and maxvpn0 recovered" in log
    assert "VLESS LAN policy restored after service recovery" in log


def test_recovers_when_sing_box_process_is_missing(tmp_path: Path) -> None:
    log, stderr, rc = _run_watchdog(
        tmp_path, scenario="recovery", process_up=False, tun_up=False, policy_up=False
    )
    assert rc == 0, stderr
    assert log.splitlines().count("service_action=start") == 1
    assert "attempting start of maxvpn-sing-box" in log
    assert log.count("route_restore") == 1


def test_healthy_state_does_not_restart_or_repair(tmp_path: Path) -> None:
    log, stderr, rc = _run_watchdog(
        tmp_path, scenario="recovery", process_up=True, tun_up=True, policy_up=True
    )
    assert rc == 0, stderr
    assert "service_action=" not in log
    assert "route_restore" not in log


def test_invalid_config_refuses_restart(tmp_path: Path) -> None:
    log, stderr, rc = _run_watchdog(
        tmp_path,
        scenario="recovery",
        process_up=True,
        tun_up=False,
        invalid_config=True,
    )
    assert rc == 0, stderr
    assert "service_action=" not in log
    assert "config check failed; refusing restart" in log
    assert "route_restore" not in log


def test_failed_service_start_keeps_route_repair_uninvoked(tmp_path: Path) -> None:
    log, stderr, rc = _run_watchdog(
        tmp_path, scenario="service-action-fails", process_up=False, tun_up=False
    )
    assert rc == 0, stderr
    assert log.count("service_action=start\n") == 1
    assert "start command failed; fail-closed policy retained" in log
    assert "route_restore" not in log


def test_timeout_waiting_for_tun_does_not_restore_routes(tmp_path: Path) -> None:
    log, stderr, rc = _run_watchdog(
        tmp_path, scenario="timeout-no-tun", process_up=False, tun_up=False
    )
    assert rc == 0, stderr
    assert log.count("service_action=start\n") == 1
    assert "start did not restore maxvpn0 within 20 seconds" in log
    assert "route_restore" not in log


def test_mode_change_during_recovery_skips_vless_route_restore(tmp_path: Path) -> None:
    log, stderr, rc = _run_watchdog(
        tmp_path, scenario="mode-switch", process_up=False, tun_up=False
    )
    assert rc == 0, stderr
    assert log.count("service_action=start\n") == 1
    assert "runtime mode changed during recovery" in log
    assert "route_restore" not in log


def test_non_vless_mode_never_restarts_sing_box(tmp_path: Path) -> None:
    log, stderr, rc = _run_watchdog(
        tmp_path, scenario="recovery", mode="wan", process_up=False, tun_up=False
    )
    assert rc == 0, stderr
    assert "service_action=" not in log
    assert "route_restore" not in log


def test_repairs_missing_ipv4_forwarding_jump_without_restarting_sing_box(
    tmp_path: Path,
) -> None:
    log, stderr, rc = _run_watchdog(
        tmp_path,
        scenario="recovery",
        process_up=True,
        tun_up=True,
        policy_up=True,
        missing_ipv4_jump=True,
    )
    assert rc == 0, stderr
    assert "service_action=" not in log
    assert log.count("route_restore") == 1
    assert "VLESS policy repaired" in log


def test_repairs_missing_ipv6_forwarding_jump_without_restarting_sing_box(
    tmp_path: Path,
) -> None:
    log, stderr, rc = _run_watchdog(
        tmp_path,
        scenario="recovery",
        process_up=True,
        tun_up=True,
        policy_up=True,
        missing_ipv6_jump=True,
    )
    assert rc == 0, stderr
    assert "service_action=" not in log
    assert log.count("route_restore") == 1
    assert "VLESS policy repaired" in log


def test_repairs_both_missing_forwarding_jumps_without_restarting_sing_box(
    tmp_path: Path,
) -> None:
    log, stderr, rc = _run_watchdog(
        tmp_path,
        scenario="recovery",
        process_up=True,
        tun_up=True,
        policy_up=True,
        missing_ipv4_jump=True,
        missing_ipv6_jump=True,
    )
    assert rc == 0, stderr
    assert "service_action=" not in log
    assert log.count("route_restore") == 1
    assert "VLESS policy repaired" in log


def test_failed_policy_repair_is_rate_limited_and_does_not_restart_sing_box(
    tmp_path: Path,
) -> None:
    log, stderr, rc = _run_watchdog(
        tmp_path,
        scenario="recovery",
        process_up=True,
        tun_up=True,
        policy_up=True,
        missing_ipv4_jump=True,
        fail_policy_repair=True,
    )
    assert rc == 0, stderr
    assert "service_action=" not in log
    assert log.count("route_restore") == 1
    assert "VLESS policy repair failed; fail-closed policy retained" in log
