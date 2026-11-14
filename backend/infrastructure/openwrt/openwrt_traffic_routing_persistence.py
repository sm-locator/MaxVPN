from __future__ import annotations

import shlex
from dataclasses import dataclass
from ipaddress import IPv4Network
from typing import Iterable

from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.models.traffic_routing_rule import (
    TrafficRoute,
    TrafficRoutingRule,
    TrafficTargetType,
)
from backend.ports.remote_command_executor import RemoteCommandExecutor


@dataclass(frozen=True, slots=True)
class TrafficRoutingPersistenceSnapshot:
    restore_script: str | None


class OpenWrtTrafficRoutingPersistence:
    """
    Persists the MaxVPN Smart Routing CIDR runtime configuration on OpenWrt.

    The persisted restore script is executed from /etc/firewall.user so that
    routing state is rebuilt after firewall reloads and reboots.
    """

    FIREWALL_USER = "/etc/firewall.user"

    MAXVPN_DIR = "/etc/maxvpn"
    RESTORE_SCRIPT = "/etc/maxvpn/traffic-routing.restore"

    HOOK_START = "# >>> MAXVPN TRAFFIC ROUTING HOOK >>>"
    HOOK_COMMAND = (
        "[ -x /etc/maxvpn/traffic-routing.restore ] "
        "&& /etc/maxvpn/traffic-routing.restore"
    )
    HOOK_END = "# <<< MAXVPN TRAFFIC ROUTING HOOK <<<"

    DIRECT_IPSET = "MAXVPN_DIRECT"
    STATIC_IPSET = "MAXVPN_DIRECT_STATIC"
    DIRECT_IPSET_V6 = "MAXVPN_DIRECT6"

    ROUTING_TABLE = 200
    FWMARK = 0x64
    FWMASK = 0xFF
    RULE_PRIORITY = 100

    MANGLE_CHAIN = "PREROUTING"

    def __init__(
        self,
        executor: RemoteCommandExecutor,
        *,
        lan_interface: str = "br-lan",
        wan_interface: str = "eth1",
        wan_gateway: str = "46.48.56.1",
    ) -> None:
        self._executor = executor
        self._lan_interface = lan_interface
        self._wan_interface = wan_interface
        self._wan_gateway = wan_gateway

    def build_install_commands(
        self,
        policy: TrafficRoutingPolicy,
    ) -> list[list[str]]:
        direct_rules = tuple(
            rule
            for rule in policy.rules
            if (
                rule.enabled
                and rule.action is TrafficRoute.DIRECT
                and rule.target_type is TrafficTargetType.CIDR
                and ":" not in rule.target
            )
        )

        restore_script = self._build_restore_script(direct_rules)
        quoted_script = shlex.quote(restore_script)

        hook = "\n".join(
            [
                self.HOOK_START,
                self.HOOK_COMMAND,
                self.HOOK_END,
            ]
        )

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
            "echo 'Invalid MaxVPN traffic routing hook markers' >&2; "
            "exit 1; "
            "fi; "
            'if [ "$start_count" -eq 1 ]; then '
            f"sed -i "
            f"'/^# >>> MAXVPN TRAFFIC ROUTING HOOK >>>$/,"
            f"/^# <<< MAXVPN TRAFFIC ROUTING HOOK <<</d' "
            f"{self.FIREWALL_USER}; "
            "fi; "
            "else "
            f"printf '%s\\n' {quoted_hook} > {self.FIREWALL_USER}; "
            "exit 0; "
            "fi; "
            f"printf '\\n%s\\n' {quoted_hook} >> {self.FIREWALL_USER}"
        )

        return [
            [
                "sh",
                "-c",
                (
                    f"mkdir -p {self.MAXVPN_DIR}; "
                    f"printf '%s\\n' {quoted_script} "
                    f"> {self.RESTORE_SCRIPT}"
                ),
            ],
            [
                "chmod",
                "755",
                self.RESTORE_SCRIPT,
            ],
            [
                "sh",
                "-c",
                normalize_hook_command,
            ],
            [
                "sh",
                "-c",
                f"{self.RESTORE_SCRIPT}",
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
            "echo 'Invalid MaxVPN traffic routing hook markers' >&2; "
            "exit 1; "
            "fi; "
            f"sed -i "
            f"'/^# >>> MAXVPN TRAFFIC ROUTING HOOK >>>$/,"
            f"/^# <<< MAXVPN TRAFFIC ROUTING HOOK <<</d' "
            f"{self.FIREWALL_USER}; "
            "fi"
        )

        remove_runtime_command = self._build_remove_runtime_command()

        return [
            [
                "sh",
                "-c",
                remove_hook_command,
            ],
            [
                "sh",
                "-c",
                remove_runtime_command,
            ],
            [
                "rm",
                "-f",
                self.RESTORE_SCRIPT,
            ],
        ]

    def capture_snapshot(self) -> TrafficRoutingPersistenceSnapshot:
        result = self._executor.run(
            [
                "sh",
                "-c",
                (
                    f"if [ -f {self.RESTORE_SCRIPT} ]; then "
                    f"cat {self.RESTORE_SCRIPT}; "
                    "else "
                    "exit 3; "
                    "fi"
                ),
            ],
        )

        if result.returncode == 3:
            return TrafficRoutingPersistenceSnapshot(
                restore_script=None,
            )

        if result.returncode != 0:
            raise RuntimeError(
                "Failed to capture Smart Routing persistence snapshot: "
                f"returncode={result.returncode}; "
                f"stderr={result.stderr!r}"
            )

        return TrafficRoutingPersistenceSnapshot(
            restore_script=result.stdout,
        )

    def restore_snapshot(
        self,
        snapshot: TrafficRoutingPersistenceSnapshot,
    ) -> None:
        if snapshot.restore_script is None:
            self.uninstall()
            return

        quoted_script = shlex.quote(snapshot.restore_script)

        commands = [
            [
                "sh",
                "-c",
                (
                    f"mkdir -p {self.MAXVPN_DIR}; "
                    f"printf '%s\\n' {quoted_script} "
                    f"> {self.RESTORE_SCRIPT}"
                ),
            ],
            [
                "chmod",
                "755",
                self.RESTORE_SCRIPT,
            ],
            [
                "sh",
                "-c",
                self.HOOK_COMMAND,
            ],
        ]

        for command in commands[:-1]:
            self._run_checked(command)

        self._run_checked(
            [
                "sh",
                "-c",
                f"{self.RESTORE_SCRIPT}",
            ],
        )

    def install(
        self,
        policy: TrafficRoutingPolicy,
    ) -> None:
        for command in self.build_install_commands(policy):
            self._run_checked(command)

    def uninstall(self) -> None:
        for command in self.build_uninstall_commands():
            self._run_checked(command)

    def _build_restore_script(
        self,
        direct_rules: Iterable[TrafficRoutingRule],
    ) -> str:
        networks = tuple(
            self._normalize_ipv4_network(rule.target) for rule in direct_rules
        )

        lines = [
            "#!/bin/sh",
            "",
            "set -u",
            "",
            (
                f"ipset create {self.DIRECT_IPSET} hash:ip "
                "family inet hashsize 1024 maxelem 65536 "
                "2>/dev/null || true"
            ),
            (
                f"ipset create {self.STATIC_IPSET} hash:ip "
                "family inet hashsize 1024 maxelem 65536 "
                "2>/dev/null || true"
            ),
            (
                f"ipset create {self.DIRECT_IPSET_V6} hash:ip "
                "family inet6 hashsize 1024 maxelem 65536 "
                "2>/dev/null || true"
            ),
            f"ipset flush {self.STATIC_IPSET}",
            (
                f"while iptables -t mangle -D {self.MANGLE_CHAIN} "
                f"-i {self._lan_interface} "
                f"-m set --match-set {self.DIRECT_IPSET} dst "
                f"-j MARK --set-xmark "
                f"0x{self.FWMARK:x}/0x{self.FWMASK:x} "
                "2>/dev/null; do :; done"
            ),
            (
                f"while iptables -t mangle -D {self.MANGLE_CHAIN} "
                f"-i {self._lan_interface} "
                f"-m set --match-set {self.DIRECT_IPSET} dst "
                f"-j MARK --set-mark "
                f"0x{self.FWMARK:x} "
                "2>/dev/null; do :; done"
            ),
            (
                f"while iptables -t mangle -D {self.MANGLE_CHAIN} "
                f"-i {self._lan_interface} "
                f"-m set --match-set {self.STATIC_IPSET} dst "
                f"-j MARK --set-xmark "
                f"0x{self.FWMARK:x}/0x{self.FWMASK:x} "
                "2>/dev/null; do :; done"
            ),
            (
                f"while iptables -t mangle -D {self.MANGLE_CHAIN} "
                f"-i {self._lan_interface} "
                f"-m set --match-set {self.STATIC_IPSET} dst "
                f"-j MARK --set-mark "
                f"0x{self.FWMARK:x} "
                "2>/dev/null; do :; done"
            ),
            (
                f"iptables -t mangle -I {self.MANGLE_CHAIN} 1 "
                f"-i {self._lan_interface} "
                f"-m set --match-set {self.STATIC_IPSET} dst "
                f"-j MARK --set-xmark "
                f"0x{self.FWMARK:x}/0x{self.FWMASK:x}"
            ),
            (
                f"iptables -t mangle -I {self.MANGLE_CHAIN} 1 "
                f"-i {self._lan_interface} "
                f"-m set --match-set {self.DIRECT_IPSET} dst "
                f"-j MARK --set-xmark "
                f"0x{self.FWMARK:x}/0x{self.FWMASK:x}"
            ),
            (f"ip route flush table {self.ROUTING_TABLE} 2>/dev/null || true"),
            (
                "ip route show table main | while IFS= read -r route; do "
                'case "$route" in '
                'default\\ *|"") continue ;; '
                "esac; "
                f"ip route add $route table {self.ROUTING_TABLE} "
                "2>/dev/null || true; "
                "done"
            ),
            (
                f"ip route add table {self.ROUTING_TABLE} "
                f"default via {self._wan_gateway} "
                f"dev {self._wan_interface}"
            ),
            (f"ip rule del priority {self.RULE_PRIORITY} 2>/dev/null || true"),
            (
                f"ip rule add priority {self.RULE_PRIORITY} "
                f"fwmark 0x{self.FWMARK:x}/0x{self.FWMASK:x} "
                f"table {self.ROUTING_TABLE}"
            ),
            "",
            (
                f"ip6tables -t mangle -D {self.MANGLE_CHAIN} "
                f"-i {self._lan_interface} "
                f"-m set --match-set {self.DIRECT_IPSET_V6} dst "
                f"-j MARK --set-mark 0x{self.FWMARK:x} "
                "2>/dev/null || true"
            ),
            (f"ip -6 rule del priority {self.RULE_PRIORITY} 2>/dev/null || true"),
            (f"ip -6 route flush table {self.ROUTING_TABLE} 2>/dev/null || true"),
            ('ipv6_default="$(ip -6 route show table main default | head -n 1)"'),
            (
                'ipv6_dev="$(printf "%s\\n" "$ipv6_default" '
                '| sed -n "s/.*dev \\([^ ]*\\).*/\\1/p")"'
            ),
            (
                'if [ -n "$ipv6_default" ] && [ -n "$ipv6_dev" ] && '
                'ip -6 addr show dev "$ipv6_dev" scope global | '
                'grep -q "inet6 "; then'
            ),
            (
                "    ip -6 route show table main | "
                "while IFS= read -r route; do "
                'case "$route" in '
                'default\\ *|"") continue ;; '
                "esac; "
                f"ip -6 route add $route table {self.ROUTING_TABLE} "
                "2>/dev/null || true; "
                "done"
            ),
            (
                '    ipv6_gateway="$(printf "%s\\n" "$ipv6_default" '
                '| sed -n "s/.*via \\([^ ]*\\).*/\\1/p")"'
            ),
            '    if [ -n "$ipv6_gateway" ]; then',
            (
                f"        ip -6 route add table {self.ROUTING_TABLE} "
                'default via "$ipv6_gateway" dev "$ipv6_dev" '
                "2>/dev/null || true"
            ),
            "    else",
            (
                f"        ip -6 route add table {self.ROUTING_TABLE} "
                'default dev "$ipv6_dev" 2>/dev/null || true'
            ),
            "    fi",
            (
                f"    ip6tables -t mangle -I {self.MANGLE_CHAIN} 1 "
                f"-i {self._lan_interface} "
                f"-m set --match-set {self.DIRECT_IPSET_V6} dst "
                f"-j MARK --set-mark 0x{self.FWMARK:x}"
            ),
            (
                f"    ip -6 rule add priority {self.RULE_PRIORITY} "
                f"fwmark 0x{self.FWMARK:x}/0x{self.FWMASK:x} "
                f"table {self.ROUTING_TABLE}"
            ),
            "fi",
        ]

        lines.extend(f"ipset add {self.STATIC_IPSET} {network}" for network in networks)

        lines.extend(
            [
                "",
                "ip route flush cache 2>/dev/null || true",
                "exit 0",
            ],
        )

        return "\n".join(lines)

    def _build_remove_runtime_command(self) -> str:
        return "; ".join(
            [
                (
                    f"while iptables -t mangle -D {self.MANGLE_CHAIN} "
                    f"-i {self._lan_interface} "
                    f"-m set --match-set {self.DIRECT_IPSET} dst "
                    f"-j MARK --set-xmark "
                    f"0x{self.FWMARK:x}/0x{self.FWMASK:x} "
                    "2>/dev/null; do :; done"
                ),
                (
                    f"while iptables -t mangle -D {self.MANGLE_CHAIN} "
                    f"-i {self._lan_interface} "
                    f"-m set --match-set {self.DIRECT_IPSET} dst "
                    f"-j MARK --set-mark "
                    f"0x{self.FWMARK:x} "
                    "2>/dev/null; do :; done"
                ),
                (
                    f"while iptables -t mangle -D {self.MANGLE_CHAIN} "
                    f"-i {self._lan_interface} "
                    f"-m set --match-set {self.STATIC_IPSET} dst "
                    f"-j MARK --set-xmark "
                    f"0x{self.FWMARK:x}/0x{self.FWMASK:x} "
                    "2>/dev/null; do :; done"
                ),
                (
                    f"while iptables -t mangle -D {self.MANGLE_CHAIN} "
                    f"-i {self._lan_interface} "
                    f"-m set --match-set {self.STATIC_IPSET} dst "
                    f"-j MARK --set-mark "
                    f"0x{self.FWMARK:x} "
                    "2>/dev/null; do :; done"
                ),
                (
                    f"ip6tables -t mangle -D {self.MANGLE_CHAIN} "
                    f"-i {self._lan_interface} "
                    f"-m set --match-set {self.DIRECT_IPSET_V6} dst "
                    f"-j MARK --set-mark 0x{self.FWMARK:x} "
                    "2>/dev/null || true"
                ),
                (f"ip rule del priority {self.RULE_PRIORITY} 2>/dev/null || true"),
                (f"ip -6 rule del priority {self.RULE_PRIORITY} 2>/dev/null || true"),
                (f"ip route flush table {self.ROUTING_TABLE} 2>/dev/null || true"),
                (f"ip -6 route flush table {self.ROUTING_TABLE} 2>/dev/null || true"),
                (f"ipset destroy {self.STATIC_IPSET} 2>/dev/null || true"),
                (f"ipset destroy {self.DIRECT_IPSET_V6} 2>/dev/null || true"),
                "ip route flush cache 2>/dev/null || true",
                "exit 0",
            ],
        )

    def _run_checked(self, command: list[str]) -> None:
        result = self._executor.run(command)

        if result.returncode != 0:
            raise RuntimeError(
                "OpenWrt traffic routing persistence command failed: "
                f"{command!r}; "
                f"returncode={result.returncode}; "
                f"stderr={result.stderr!r}"
            )

    @staticmethod
    def _normalize_ipv4_network(target: str) -> str:
        return str(
            IPv4Network(
                target,
                strict=False,
            ),
        )
