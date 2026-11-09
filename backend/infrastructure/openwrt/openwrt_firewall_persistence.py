from __future__ import annotations

import shlex

from backend.infrastructure.openwrt.openwrt_firewall_script_renderer import (
    OpenWrtFirewallScriptRenderer,
)
from backend.infrastructure.openwrt.openwrt_lan_vpn_command_renderer import (
    OpenWrtLanVpnCommandRenderer,
)
from backend.infrastructure.openwrt.openwrt_lan_vpn_hotplug_renderer import (
    OpenWrtLanVpnHotplugRenderer,
)
from backend.models.vpn_traffic_policy import VpnTrafficPolicy
from backend.ports.remote_command_executor import RemoteCommandExecutor
from backend.services.openwrt_firewall_reload import (
    OpenWrtFirewallReloadResult,
    OpenWrtFirewallReloadService,
)


class OpenWrtFirewallPersistence:
    """
    Installs and removes the persistent MaxVPN firewall hook on OpenWrt.
    """

    FIREWALL_USER = "/etc/firewall.user"
    MAXVPN_DIR = "/etc/maxvpn"
    MAXVPN_SCRIPT = "/etc/maxvpn/firewall.user"

    BACKUP_SCRIPT = "/etc/maxvpn/firewall.user.backup"
    BACKUP_RELOAD = "/etc/maxvpn/firewall.user.reload.backup"

    LAN_VPN_HOTPLUG = "/etc/hotplug.d/iface/99-lan-vpn"
    LAN_VPN_HOTPLUG_BACKUP = "/etc/maxvpn/99-lan-vpn.backup"
    LAN_VPN_ON = "/usr/bin/vpn-lan-on"
    LAN_VPN_OFF = "/usr/bin/vpn-lan-off"
    LAN_VPN_VLESS_ON = "/usr/bin/vpn-lan-vless-on"
    LAN_VPN_VLESS_STOP = OpenWrtLanVpnCommandRenderer.VLESS_STOP
    LAN_VPN_ON_BACKUP = "/etc/maxvpn/vpn-lan-on.backup"
    LAN_VPN_OFF_BACKUP = "/etc/maxvpn/vpn-lan-off.backup"
    LAN_VPN_VLESS_ON_BACKUP = "/etc/maxvpn/vpn-lan-vless-on.backup"
    LAN_VPN_VLESS_STOP_BACKUP = "/etc/maxvpn/vpn-lan-vless-stop.backup"
    VLESS_RESTORE_INIT = "/etc/init.d/maxvpn-vless-routing-restore"
    VLESS_RESTORE_INIT_BACKUP = "/etc/maxvpn/maxvpn-vless-routing-restore.init.backup"
    VLESS_WATCHDOG = "/usr/bin/maxvpn-vless-watchdog"
    VLESS_WATCHDOG_BACKUP = "/etc/maxvpn/maxvpn-vless-watchdog.backup"
    VLESS_WATCHDOG_INIT = "/etc/init.d/maxvpn-vless-watchdog"
    VLESS_WATCHDOG_INIT_BACKUP = "/etc/maxvpn/maxvpn-vless-watchdog.init.backup"

    HOOK_START = "# >>> MAXVPN FIREWALL HOOK >>>"
    HOOK_COMMAND = "[ -x /etc/maxvpn/firewall.user ] && /etc/maxvpn/firewall.user"
    HOOK_END = "# <<< MAXVPN FIREWALL HOOK <<<"

    def __init__(
        self,
        executor: RemoteCommandExecutor,
        renderer: OpenWrtFirewallScriptRenderer | None = None,
        reload_service: OpenWrtFirewallReloadService | None = None,
        lan_vpn_hotplug_renderer: OpenWrtLanVpnHotplugRenderer | None = None,
    ) -> None:
        self._executor = executor
        self._renderer = renderer or OpenWrtFirewallScriptRenderer()
        self._reload_service = reload_service
        self._lan_vpn_hotplug_renderer = (
            lan_vpn_hotplug_renderer or OpenWrtLanVpnHotplugRenderer()
        )

    def build_install_commands(
        self,
        policy: VpnTrafficPolicy,
        *,
        start_watchdog: bool = True,
    ) -> list[list[str]]:
        script = self._renderer.render(policy)

        hotplug_script = self._lan_vpn_hotplug_renderer.render()
        quoted_hotplug_script = shlex.quote(hotplug_script)

        lan_vpn_command_renderer = OpenWrtLanVpnCommandRenderer()
        lan_vpn_on_script = lan_vpn_command_renderer.render_on()
        lan_vpn_off_script = lan_vpn_command_renderer.render_off()
        lan_vpn_vless_on_script = lan_vpn_command_renderer.render_vless_on()
        quoted_vless_stop_script = shlex.quote(
            lan_vpn_command_renderer.render_vless_stop()
        )
        vless_restore_init_script = lan_vpn_command_renderer.render_vless_restore_init()
        vless_watchdog_script = lan_vpn_command_renderer.render_vless_watchdog()
        vless_watchdog_init_script = (
            lan_vpn_command_renderer.render_vless_watchdog_init()
        )
        quoted_lan_vpn_on_script = shlex.quote(lan_vpn_on_script)
        quoted_lan_vpn_off_script = shlex.quote(lan_vpn_off_script)
        quoted_lan_vpn_vless_on_script = shlex.quote(lan_vpn_vless_on_script)
        quoted_vless_restore_init_script = shlex.quote(vless_restore_init_script)
        quoted_vless_watchdog_script = shlex.quote(vless_watchdog_script)
        quoted_vless_watchdog_init_script = shlex.quote(vless_watchdog_init_script)

        hook = "\n".join(
            [
                self.HOOK_START,
                self.HOOK_COMMAND,
                self.HOOK_END,
            ]
        )

        quoted_script = shlex.quote(script)
        quoted_hook = shlex.quote(hook)
        quoted_start = shlex.quote(self.HOOK_START)
        quoted_end = shlex.quote(self.HOOK_END)

        normalize_hook_command = (
            f"if [ -f {self.FIREWALL_USER} ]; then "
            f"start_count=$(grep -F -c {quoted_start} "
            f"{self.FIREWALL_USER} 2>/dev/null || true); "
            f"end_count=$(grep -F -c {quoted_end} "
            f"{self.FIREWALL_USER} 2>/dev/null || true); "
            'if [ "$start_count" -gt 1 ] || '
            '[ "$end_count" -gt 1 ] || '
            '[ "$start_count" -ne "$end_count" ]; then '
            "echo 'Invalid MaxVPN firewall hook markers' >&2; "
            "exit 1; "
            "fi; "
            'if [ "$start_count" -eq 1 ]; then '
            f"sed -i "
            f"'/^# >>> MAXVPN FIREWALL HOOK >>>$/,"
            f"/^# <<< MAXVPN FIREWALL HOOK <<</d' "
            f"{self.FIREWALL_USER}; "
            "fi; "
            "fi; "
            f"hook=$(printf '%s\\n' {quoted_hook}); "
            f'printf "\\n%s\\n" "$hook" >> {self.FIREWALL_USER}'
        )

        backup_command = (
            f"mkdir -p {self.MAXVPN_DIR} "
            f"$(dirname {self.LAN_VPN_HOTPLUG}); "
            f"if [ -f {self.LAN_VPN_HOTPLUG} ] && "
            f"[ ! -f {self.LAN_VPN_HOTPLUG_BACKUP} ]; then "
            f"cp {self.LAN_VPN_HOTPLUG} "
            f"{self.LAN_VPN_HOTPLUG_BACKUP}; "
            "fi; "
            f"if [ -f {self.LAN_VPN_ON} ] && "
            f"[ ! -f {self.LAN_VPN_ON_BACKUP} ]; then "
            f"cp {self.LAN_VPN_ON} {self.LAN_VPN_ON_BACKUP}; "
            "fi; "
            f"if [ -f {self.LAN_VPN_OFF} ] && "
            f"[ ! -f {self.LAN_VPN_OFF_BACKUP} ]; then "
            f"cp {self.LAN_VPN_OFF} {self.LAN_VPN_OFF_BACKUP}; "
            "fi; "
            f"if [ -f {self.FIREWALL_USER} ] && "
            f"[ ! -f {self.BACKUP_SCRIPT} ]; then "
            f"cp {self.FIREWALL_USER} {self.BACKUP_SCRIPT}; "
            "fi; "
            f"if [ -f {self.LAN_VPN_VLESS_ON} ] && "
            f"[ ! -f {self.LAN_VPN_VLESS_ON_BACKUP} ]; then "
            f"cp {self.LAN_VPN_VLESS_ON} {self.LAN_VPN_VLESS_ON_BACKUP}; "
            "fi; "
            f"if [ -f {self.LAN_VPN_VLESS_STOP} ] && "
            f"[ ! -f {self.LAN_VPN_VLESS_STOP_BACKUP} ]; then "
            f"cp {self.LAN_VPN_VLESS_STOP} {self.LAN_VPN_VLESS_STOP_BACKUP}; "
            "fi; "
            f"if [ -f {self.VLESS_RESTORE_INIT} ] && "
            f"[ ! -f {self.VLESS_RESTORE_INIT_BACKUP} ]; then "
            f"cp {self.VLESS_RESTORE_INIT} {self.VLESS_RESTORE_INIT_BACKUP}; "
            "fi; "
            f"if [ -f {self.VLESS_WATCHDOG} ] && "
            f"[ ! -f {self.VLESS_WATCHDOG_BACKUP} ]; then "
            f"cp {self.VLESS_WATCHDOG} {self.VLESS_WATCHDOG_BACKUP}; "
            "fi; "
            f"if [ -f {self.VLESS_WATCHDOG_INIT} ] && "
            f"[ ! -f {self.VLESS_WATCHDOG_INIT_BACKUP} ]; then "
            f"cp {self.VLESS_WATCHDOG_INIT} {self.VLESS_WATCHDOG_INIT_BACKUP}; "
            "fi"
        )

        return [
            [
                "sh",
                "-c",
                backup_command,
            ],
            [
                "sh",
                "-c",
                f"printf '%s\\n' {quoted_hotplug_script} > {self.LAN_VPN_HOTPLUG}",
            ],
            [
                "chmod",
                "755",
                self.LAN_VPN_HOTPLUG,
            ],
            [
                "sh",
                "-c",
                f"printf '%s\\n' {quoted_script} > {self.MAXVPN_SCRIPT}",
            ],
            [
                "chmod",
                "755",
                self.MAXVPN_SCRIPT,
            ],
            [
                "sh",
                "-c",
                normalize_hook_command,
            ],
            self._build_backup_firewall_user_reload_command(),
            self._build_ensure_firewall_user_reload_command(),
            [
                "sh",
                "-c",
                f"printf '%s\\n' {quoted_lan_vpn_on_script} > {self.LAN_VPN_ON}",
            ],
            [
                "chmod",
                "755",
                self.LAN_VPN_ON,
            ],
            [
                "sh",
                "-c",
                f"printf '%s\\n' {quoted_lan_vpn_off_script} > {self.LAN_VPN_OFF}",
            ],
            [
                "chmod",
                "755",
                self.LAN_VPN_OFF,
            ],
            [
                "sh",
                "-c",
                f"printf '%s\\n' {quoted_lan_vpn_vless_on_script} > {self.LAN_VPN_VLESS_ON}",  # noqa: E501
            ],
            [
                "chmod",
                "755",
                self.LAN_VPN_VLESS_ON,
            ],
            [
                "sh",
                "-c",
                (
                    f"set -e; tmp=$(mktemp {self.LAN_VPN_VLESS_STOP}.XXXXXX); "
                    """trap 'rm -f "$tmp"' EXIT; """
                    f"""printf '%s\\n' {quoted_vless_stop_script} > "$tmp"; """
                    f"""chmod 755 "$tmp"; mv "$tmp" {self.LAN_VPN_VLESS_STOP}"""
                ),
            ],
            [
                "sh",
                "-c",
                f"printf '%s\\n' {quoted_vless_restore_init_script} > {self.VLESS_RESTORE_INIT}",  # noqa: E501
            ],
            ["chmod", "755", self.VLESS_RESTORE_INIT],
            # Keep the blocking restore hook out of boot; watchdog retries.
            ["sh", "-c", f"{self.VLESS_RESTORE_INIT} disable"],
            ["sh", "-c", f"{self.VLESS_WATCHDOG_INIT} stop 2>/dev/null || true"],
            [
                "sh",
                "-c",
                f"printf '%s\n' {quoted_vless_watchdog_script} > {self.VLESS_WATCHDOG}",
            ],
            ["chmod", "755", self.VLESS_WATCHDOG],
            [
                "sh",
                "-c",
                f"printf '%s\n' {quoted_vless_watchdog_init_script} > {self.VLESS_WATCHDOG_INIT}",  # noqa: E501
            ],
            ["chmod", "755", self.VLESS_WATCHDOG_INIT],
            [
                "sh",
                "-c",
                (
                    f"{self.VLESS_WATCHDOG_INIT} enable && "
                    f"{self.VLESS_WATCHDOG_INIT} start"
                    if start_watchdog
                    else f"{self.VLESS_WATCHDOG_INIT} enable"
                ),
            ],
        ]

    def build_uninstall_commands(self) -> list[list[str]]:
        quoted_start = shlex.quote(self.HOOK_START)
        quoted_end = shlex.quote(self.HOOK_END)

        remove_hook_command = (
            f"if [ -f {self.FIREWALL_USER} ]; then "
            f"start_count=$(grep -F -c {quoted_start} "
            f"{self.FIREWALL_USER} 2>/dev/null || true); "
            f"end_count=$(grep -F -c {quoted_end} "
            f"{self.FIREWALL_USER} 2>/dev/null || true); "
            'if [ "$start_count" -eq 0 ] && '
            '[ "$end_count" -eq 0 ]; then '
            "exit 0; "
            "fi; "
            'if [ "$start_count" -ne 1 ] || '
            '[ "$end_count" -ne 1 ]; then '
            "echo 'Invalid MaxVPN firewall hook markers' >&2; "
            "exit 1; "
            "fi; "
            f"sed -i "
            f"'/^# >>> MAXVPN FIREWALL HOOK >>>$/,"
            f"/^# <<< MAXVPN FIREWALL HOOK <<</d' "
            f"{self.FIREWALL_USER}; "
            "fi"
        )

        remove_ipv4_runtime_command = (
            "while iptables -D forwarding_rule "
            "-j MAXVPN_LAN_FORWARD 2>/dev/null; do :; done; "
            "iptables -F MAXVPN_LAN_FORWARD 2>/dev/null || true; "
            "iptables -X MAXVPN_LAN_FORWARD 2>/dev/null || true; "
            "if iptables -S MAXVPN_LAN_FORWARD "
            ">/dev/null 2>&1; then "
            "echo 'MAXVPN IPv4 chain still exists' >&2; "
            "exit 1; "
            "fi; "
            "if iptables -S forwarding_rule "
            "| grep -F -- '-j MAXVPN_LAN_FORWARD' "
            ">/dev/null 2>&1; then "
            "echo 'MAXVPN IPv4 jump still exists' >&2; "
            "exit 1; "
            "fi"
        )

        remove_ipv6_runtime_command = (
            "while ip6tables -D forwarding_rule "
            "-j MAXVPN_LAN6_FORWARD 2>/dev/null; do :; done; "
            "ip6tables -F MAXVPN_LAN6_FORWARD 2>/dev/null || true; "
            "ip6tables -X MAXVPN_LAN6_FORWARD 2>/dev/null || true; "
            "if ip6tables -S MAXVPN_LAN6_FORWARD "
            ">/dev/null 2>&1; then "
            "echo 'MAXVPN IPv6 chain still exists' >&2; "
            "exit 1; "
            "fi; "
            "if ip6tables -S forwarding_rule "
            "| grep -F -- '-j MAXVPN_LAN6_FORWARD' "
            ">/dev/null 2>&1; then "
            "echo 'MAXVPN IPv6 jump still exists' >&2; "
            "exit 1; "
            "fi"
        )

        restore_reload_command = self._build_restore_firewall_user_reload_command()

        restore_lan_vpn_vless_on_command = (
            f"if [ -f {self.LAN_VPN_VLESS_ON_BACKUP} ]; then "
            f"mv {self.LAN_VPN_VLESS_ON_BACKUP} {self.LAN_VPN_VLESS_ON}; "
            "else "
            f"rm -f {self.LAN_VPN_VLESS_ON}; "
            "fi"
        )

        disable_vless_restore_init_command = (
            f"{self.VLESS_RESTORE_INIT} disable 2>/dev/null || true"
        )
        restore_vless_restore_init_command = (
            f"if [ -f {self.VLESS_RESTORE_INIT_BACKUP} ]; then "
            f"mv {self.VLESS_RESTORE_INIT_BACKUP} {self.VLESS_RESTORE_INIT}; "
            f"chmod 755 {self.VLESS_RESTORE_INIT}; "
            f"{self.VLESS_RESTORE_INIT} enable; "
            "else "
            f"rm -f {self.VLESS_RESTORE_INIT}; "
            "fi"
        )

        disable_vless_watchdog_init_command = (
            f"{self.VLESS_WATCHDOG_INIT} stop 2>/dev/null || true; "
            f"{self.VLESS_WATCHDOG_INIT} disable 2>/dev/null || true"
        )
        restore_vless_watchdog_command = (
            f"if [ -f {self.VLESS_WATCHDOG_BACKUP} ]; then "
            f"mv {self.VLESS_WATCHDOG_BACKUP} {self.VLESS_WATCHDOG}; "
            f"chmod 755 {self.VLESS_WATCHDOG}; "
            "else "
            f"rm -f {self.VLESS_WATCHDOG}; "
            "fi"
        )
        restore_vless_watchdog_init_command = (
            f"if [ -f {self.VLESS_WATCHDOG_INIT_BACKUP} ]; then "
            f"mv {self.VLESS_WATCHDOG_INIT_BACKUP} {self.VLESS_WATCHDOG_INIT}; "
            f"chmod 755 {self.VLESS_WATCHDOG_INIT}; "
            f"{self.VLESS_WATCHDOG_INIT} enable; "
            "else "
            f"rm -f {self.VLESS_WATCHDOG_INIT}; "
            "fi"
        )

        restore_lan_vpn_hotplug_command = (
            f"if [ -f {self.LAN_VPN_HOTPLUG_BACKUP} ]; then "
            f"mv {self.LAN_VPN_HOTPLUG_BACKUP} {self.LAN_VPN_HOTPLUG}; "
            "else "
            f"rm -f {self.LAN_VPN_HOTPLUG}; "
            "fi"
        )

        restore_lan_vpn_on_command = (
            f"if [ -f {self.LAN_VPN_ON_BACKUP} ]; then "
            f"mv {self.LAN_VPN_ON_BACKUP} {self.LAN_VPN_ON}; "
            "else "
            f"rm -f {self.LAN_VPN_ON}; "
            "fi"
        )

        restore_lan_vpn_off_command = (
            f"if [ -f {self.LAN_VPN_OFF_BACKUP} ]; then "
            f"mv {self.LAN_VPN_OFF_BACKUP} {self.LAN_VPN_OFF}; "
            "else "
            f"rm -f {self.LAN_VPN_OFF}; "
            "fi"
        )
        restore_vless_stop_command = (
            f"if [ -f {self.LAN_VPN_VLESS_STOP_BACKUP} ]; then "
            f"mv {self.LAN_VPN_VLESS_STOP_BACKUP} {self.LAN_VPN_VLESS_STOP}; "
            "else "
            f"rm -f {self.LAN_VPN_VLESS_STOP}; "
            "fi"
        )

        return [
            ["sh", "-c", disable_vless_watchdog_init_command],
            [
                "sh",
                "-c",
                remove_hook_command,
            ],
            [
                "sh",
                "-c",
                remove_ipv4_runtime_command,
            ],
            [
                "sh",
                "-c",
                remove_ipv6_runtime_command,
            ],
            [
                "sh",
                "-c",
                restore_lan_vpn_on_command,
            ],
            [
                "sh",
                "-c",
                restore_lan_vpn_off_command,
            ],
            ["sh", "-c", restore_vless_stop_command],
            [
                "sh",
                "-c",
                disable_vless_restore_init_command,
            ],
            [
                "sh",
                "-c",
                restore_vless_restore_init_command,
            ],
            ["sh", "-c", restore_vless_watchdog_command],
            ["sh", "-c", restore_vless_watchdog_init_command],
            [
                "sh",
                "-c",
                restore_lan_vpn_vless_on_command,
            ],
            [
                "sh",
                "-c",
                restore_lan_vpn_hotplug_command,
            ],
            restore_reload_command,
            [
                "rm",
                "-f",
                self.MAXVPN_SCRIPT,
            ],
            [
                "rm",
                "-rf",
                self.MAXVPN_DIR,
            ],
        ]

    def install(
        self,
        policy: VpnTrafficPolicy,
    ) -> OpenWrtFirewallReloadResult | None:
        for command in self.build_install_commands(policy):
            self._run_checked(command)

        if self._reload_service is None:
            return None

        reload_result = self._reload_service.reload()

        if not reload_result.healthy:
            raise RuntimeError(
                "MaxVPN persistent firewall installation failed "
                "runtime verification: "
                f"{reload_result.reason}"
            )

        return reload_result

    def install_vless_runtime_support(self, policy: VpnTrafficPolicy) -> None:
        """Install VLESS support and enable watchdog for boot, without starting it.

        The traffic controller starts the watchdog only after the VLESS LAN
        activation helper has finished. This prevents the watchdog from racing
        that helper while it is applying and verifying the runtime policy.
        No global fw3 reload or legacy WireGuard verifier is invoked here.
        """
        for command in self.build_install_commands(policy, start_watchdog=False):
            self._run_checked(command)

    def start_vless_watchdog(self) -> None:
        """Start the VLESS watchdog after the LAN activation attempt."""
        self._run_checked([self.VLESS_WATCHDOG_INIT, "start"])

    def uninstall(self) -> None:
        for command in self.build_uninstall_commands():
            self._run_checked(command)

    def _run_checked(self, command: list[str]) -> None:
        result = self._executor.run(command)

        if result.returncode != 0:
            raise RuntimeError(
                "OpenWrt firewall persistence command failed: "
                f"{command!r}; "
                f"returncode={result.returncode}; "
                f"stderr={result.stderr!r}"
            )

    def _build_backup_firewall_user_reload_command(self) -> list[str]:
        return [
            "sh",
            "-c",
            (
                f"mkdir -p {self.MAXVPN_DIR}; "
                f"if [ -f {self.BACKUP_RELOAD} ]; then "
                "exit 0; "
                "fi; "
                "section=$(uci show firewall 2>/dev/null | "
                "sed -n "
                '"s/^\\(firewall\\.[^.]*\\)\\.path='
                "'\\/etc\\/firewall\\.user'$/\\1/p\" "
                "| head -n 1); "
                'if [ -n "$section" ]; then '
                'if uci -q get "$section.reload" >/dev/null 2>&1; then '
                'reload=$(uci -q get "$section.reload"); '
                f'printf "%s" "$reload" > {self.BACKUP_RELOAD}; '
                "else "
                f'printf "%s" "UNSET" > {self.BACKUP_RELOAD}; '
                "fi; "
                "else "
                f'printf "%s" "ABSENT" > {self.BACKUP_RELOAD}; '
                "fi"
            ),
        ]

    def _build_ensure_firewall_user_reload_command(self) -> list[str]:
        return [
            "sh",
            "-c",
            (
                "section=$(uci show firewall 2>/dev/null | "
                "sed -n "
                '"s/^\\(firewall\\.[^.]*\\)\\.path='
                "'\\/etc\\/firewall\\.user'$/\\1/p\" "
                "| head -n 1); "
                'if [ -n "$section" ]; then '
                'uci set "$section.reload=1"; '
                "else "
                "section=$(uci add firewall include); "
                f'uci set "$section.path={self.FIREWALL_USER}"; '
                'uci set "$section.reload=1"; '
                "fi; "
                "uci commit firewall"
            ),
        ]

    def _build_restore_firewall_user_reload_command(self) -> list[str]:
        return [
            "sh",
            "-c",
            (
                f"if [ ! -f {self.BACKUP_RELOAD} ]; then "
                "exit 0; "
                "fi; "
                f"saved=$(cat {self.BACKUP_RELOAD}); "
                "section=$(uci show firewall 2>/dev/null | "
                "sed -n "
                '"s/^\\(firewall\\.[^.]*\\)\\.path='
                "'\\/etc\\/firewall\\.user'$/\\1/p\" "
                "| head -n 1); "
                'if [ "$saved" = "ABSENT" ]; then '
                'if [ -n "$section" ]; then '
                'uci delete "$section"; '
                "uci commit firewall; "
                "fi; "
                "exit 0; "
                "fi; "
                'if [ -n "$section" ]; then '
                'if [ "$saved" = "UNSET" ]; then '
                'uci delete "$section.reload" 2>/dev/null || true; '
                "else "
                'uci set "$section.reload=$saved"; '
                "fi; "
                "uci commit firewall; "
                "fi"
            ),
        ]
