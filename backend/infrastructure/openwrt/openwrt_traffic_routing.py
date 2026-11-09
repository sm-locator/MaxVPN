from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Network, IPv6Network
from typing import Iterable

from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.models.traffic_routing_rule import (
    TrafficRoute,
    TrafficRoutingRule,
    TrafficTargetType,
)
from backend.ports.remote_command_executor import RemoteCommandExecutor


@dataclass(frozen=True, slots=True)
class OpenWrtTrafficRoutingResult:
    healthy: bool
    direct_ipset_exists: bool
    direct_rule_count: int
    routing_table_exists: bool
    direct_route_exists: bool
    reason: str | None = None


class OpenWrtTrafficRoutingService:
    """
    Applies the MaxVPN Smart Routing CIDR datapath on OpenWrt.

    VPN remains the default route through the main table.
    DIRECT destinations are placed into an ipset, marked in
    mangle/PREROUTING and resolved through routing table 200.
    """

    DIRECT_IPSET = "MAXVPN_DIRECT"
    STATIC_IPSET = "MAXVPN_DIRECT_STATIC"

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

    def apply(self, policy: TrafficRoutingPolicy) -> None:
        direct_rules = tuple(
            rule
            for rule in policy.rules
            if (
                rule.enabled
                and rule.action is TrafficRoute.DIRECT
                and rule.target_type is TrafficTargetType.CIDR
            )
        )

        self._run(
            [
                "sh",
                "-c",
                self._build_apply_command(direct_rules),
            ],
        )

    def remove(self) -> None:
        self._run(
            [
                "sh",
                "-c",
                self._build_remove_command(),
            ],
        )

    def verify(self) -> OpenWrtTrafficRoutingResult:
        ipset_result = self._run(
            [
                "ipset",
                "list",
                self.DIRECT_IPSET,
            ],
            check=False,
        )

        static_ipset_result = self._run(
            [
                "ipset",
                "list",
                self.STATIC_IPSET,
            ],
            check=False,
        )

        rule_result = self._run(
            [
                "iptables",
                "-t",
                "mangle",
                "-S",
                self.MANGLE_CHAIN,
            ],
            check=False,
        )

        table_result = self._run(
            [
                "ip",
                "route",
                "show",
                "table",
                str(self.ROUTING_TABLE),
            ],
            check=False,
        )

        policy_result = self._run(
            [
                "ip",
                "rule",
                "show",
            ],
            check=False,
        )

        ipset_output = ipset_result.stdout or ""
        static_ipset_output = static_ipset_result.stdout or ""
        mangle_output = rule_result.stdout or ""
        table_output = table_result.stdout or ""
        policy_output = policy_result.stdout or ""

        direct_ipset_exists = (
            ipset_result.returncode == 0
            and "Type: hash:ip" in ipset_output
            and "Header: family inet" in ipset_output
        )

        static_ipset_exists = (
            static_ipset_result.returncode == 0
            and "Type: hash:ip" in static_ipset_output
            and "Header: family inet" in static_ipset_output
        )

        direct_rule_count = self._count_direct_rules(mangle_output)

        expected_direct_rule_interface = f"-i {self._lan_interface}"
        direct_rule_lines = [
            line
            for line in mangle_output.splitlines()
            if (
                "--match-set MAXVPN_DIRECT dst" in line
                and "MARK" in line
                and expected_direct_rule_interface in line
            )
        ]

        static_rule_lines = [
            line
            for line in mangle_output.splitlines()
            if (
                "MAXVPN_DIRECT_STATIC" in line
                and "MARK" in line
                and expected_direct_rule_interface in line
            )
        ]

        if direct_rule_count != (len(direct_rule_lines) + len(static_rule_lines)):
            direct_rule_count = 0

        expected_direct_route = (
            f"default via {self._wan_gateway} dev {self._wan_interface}"
        )

        direct_route_exists = any(
            line.strip() == expected_direct_route for line in table_output.splitlines()
        )

        routing_table_exists = table_result.returncode == 0 and bool(
            table_output.strip()
        )

        expected_fwmark_rule = (
            f"fwmark 0x{self.FWMARK:x}/0x{self.FWMASK:x} lookup {self.ROUTING_TABLE}"
        )

        fwmark_rule_count = sum(
            1 for line in policy_output.splitlines() if expected_fwmark_rule in line
        )

        failed_checks: list[str] = []

        if not direct_ipset_exists:
            failed_checks.append("direct_ipset")

        if not static_ipset_exists:
            failed_checks.append("static_ipset")

        if len(direct_rule_lines) != 1:
            failed_checks.append(
                f"direct_mangle_rule_count={len(direct_rule_lines)}",
            )

        if len(static_rule_lines) != 1:
            failed_checks.append(
                f"static_mangle_rule_count={len(static_rule_lines)}",
            )

        if not routing_table_exists:
            failed_checks.append("routing_table")

        if not direct_route_exists:
            failed_checks.append("direct_route")

        if fwmark_rule_count != 1:
            failed_checks.append(
                f"direct_fwmark_rule_count={fwmark_rule_count}",
            )

        return OpenWrtTrafficRoutingResult(
            healthy=not failed_checks,
            direct_ipset_exists=direct_ipset_exists,
            direct_rule_count=direct_rule_count,
            routing_table_exists=routing_table_exists,
            direct_route_exists=direct_route_exists,
            reason=(
                None
                if not failed_checks
                else "traffic_routing_verification_failed: " + ", ".join(failed_checks)
            ),
        )

    def _build_apply_command(
        self,
        direct_rules: Iterable[TrafficRoutingRule],
    ) -> str:
        networks = tuple(
            self._normalize_network(rule.target)
            for rule in direct_rules
            if ":" not in rule.target
        )

        lines = [
            "set -u",
            (
                f"ipset create {self.STATIC_IPSET} hash:ip "
                "family inet hashsize 1024 maxelem 65536 "
                "2>/dev/null || true"
            ),
            f"ipset flush {self.STATIC_IPSET}",
            (
                f"iptables -t mangle -D {self.MANGLE_CHAIN} "
                f"-i {self._lan_interface} "
                f"-m set --match-set {self.DIRECT_IPSET} dst "
                f"-j MARK --set-mark 0x{self.FWMARK:x} "
                "2>/dev/null || true"
            ),
            (
                f"iptables -t mangle -D {self.MANGLE_CHAIN} "
                f"-i {self._lan_interface} "
                f"-m set --match-set {self.STATIC_IPSET} dst "
                f"-j MARK --set-mark 0x{self.FWMARK:x} "
                "2>/dev/null || true"
            ),
            (
                f"iptables -t mangle -I {self.MANGLE_CHAIN} 1 "
                f"-i {self._lan_interface} "
                f"-m set --match-set {self.STATIC_IPSET} dst "
                f"-j MARK --set-mark 0x{self.FWMARK:x}"
            ),
            (
                f"iptables -t mangle -I {self.MANGLE_CHAIN} 1 "
                f"-i {self._lan_interface} "
                f"-m set --match-set {self.DIRECT_IPSET} dst "
                f"-j MARK --set-mark 0x{self.FWMARK:x}"
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
        ]

        for network in networks:
            lines.append(
                f"ipset add {self.STATIC_IPSET} {network}",
            )

        lines.append(
            "ip route flush cache 2>/dev/null || true",
        )
        lines.append("exit 0")

        return "\n".join(lines)

    def _build_remove_command(self) -> str:
        return "; ".join(
            [
                (
                    f"iptables -t mangle -D {self.MANGLE_CHAIN} "
                    f"-i {self._lan_interface} "
                    f"-m set --match-set {self.DIRECT_IPSET} dst "
                    f"-j MARK --set-mark 0x{self.FWMARK:x} "
                    "2>/dev/null || true"
                ),
                (
                    f"iptables -t mangle -D {self.MANGLE_CHAIN} "
                    f"-i {self._lan_interface} "
                    f"-m set --match-set {self.STATIC_IPSET} dst "
                    f"-j MARK --set-mark 0x{self.FWMARK:x} "
                    "2>/dev/null || true"
                ),
                (f"ip rule del priority {self.RULE_PRIORITY} 2>/dev/null || true"),
                (f"ip route flush table {self.ROUTING_TABLE} 2>/dev/null || true"),
                (f"ipset destroy {self.STATIC_IPSET} 2>/dev/null || true"),
                "ip route flush cache 2>/dev/null || true",
                "exit 0",
            ],
        )

    def _run(
        self,
        command: list[str],
        *,
        check: bool = True,
    ):
        result = self._executor.run(command)

        if check and result.returncode != 0:
            raise RuntimeError(
                "OpenWrt traffic routing command failed: "
                f"{command!r}; "
                f"returncode={result.returncode}; "
                f"stderr={result.stderr!r}",
            )

        return result

    @staticmethod
    def _normalize_network(
        target: str,
    ) -> str:
        if ":" in target:
            network = IPv6Network(
                target,
                strict=False,
            )
            return str(network)

        network = IPv4Network(
            target,
            strict=False,
        )
        return str(network)

    @staticmethod
    def _count_direct_rules(
        rules: str,
    ) -> int:
        markers = (
            "-m set --match-set MAXVPN_DIRECT dst -j MARK --set-xmark 0x64/0xff",
            "-m set --match-set MAXVPN_DIRECT dst -j MARK --set-mark 0x64",
            "-m set --match-set MAXVPN_DIRECT_STATIC dst -j MARK --set-xmark 0x64/0xff",
            "-m set --match-set MAXVPN_DIRECT_STATIC dst -j MARK --set-mark 0x64",
        )

        return sum(
            1
            for line in rules.splitlines()
            if any(marker in line for marker in markers)
        )
