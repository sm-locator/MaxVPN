from __future__ import annotations

from backend.models.vpn_traffic_policy import VpnTrafficPolicy
from backend.ports.remote_command_executor import RemoteCommandExecutor
from backend.ports.vpn_firewall_executor import VpnFirewallExecutor


class OpenWrtFirewallExecutor(VpnFirewallExecutor):
    """
    Builds and applies a dedicated fail-closed firewall policy on OpenWrt.

    The policy is attached to fw3's forwarding_rule chain so that:
    - parental-control rules remain first;
    - MAC blocking remains first;
    - VPN fail-closed rules run before RELATED,ESTABLISHED.
    """

    IPV4_CHAIN = "MAXVPN_LAN_FORWARD"
    IPV6_CHAIN = "MAXVPN_LAN6_FORWARD"

    FORWARD_RULE_CHAIN = "forwarding_rule"

    def __init__(
        self,
        executor: RemoteCommandExecutor,
    ) -> None:
        self._executor = executor

    def build_commands(
        self,
        policy: VpnTrafficPolicy,
    ) -> list[list[str]]:
        commands: list[list[str]] = []

        commands.extend(
            self._build_family_commands(
                binary="iptables",
                chain=self.IPV4_CHAIN,
                policy=policy,
            )
        )

        commands.extend(
            self._build_family_commands(
                binary="ip6tables",
                chain=self.IPV6_CHAIN,
                policy=policy,
            )
        )

        return commands

    def _build_family_commands(
        self,
        *,
        binary: str,
        chain: str,
        policy: VpnTrafficPolicy,
    ) -> list[list[str]]:
        commands: list[list[str]] = []

        commands.append(
            [
                binary,
                "-N",
                chain,
            ]
        )

        commands.append(
            [
                binary,
                "-F",
                chain,
            ]
        )

        if policy.allow_lan_to_vpn:
            commands.append(
                [
                    binary,
                    "-A",
                    chain,
                    "-i",
                    policy.lan_interface,
                    "-o",
                    policy.vpn_interface,
                    "-j",
                    "ACCEPT",
                ]
            )

        if not policy.allow_lan_to_wan:
            commands.append(
                [
                    binary,
                    "-A",
                    chain,
                    "-i",
                    policy.lan_interface,
                    "-o",
                    policy.wan_interface,
                    "-j",
                    "DROP",
                ]
            )

        if policy.allow_lan_to_wan_ipv6 and binary == "ip6tables":
            commands.append(
                [
                    binary,
                    "-A",
                    chain,
                    "-i",
                    policy.lan_interface,
                    "-o",
                    policy.wan_interface,
                    "-j",
                    "ACCEPT",
                ]
            )

        commands.append(
            [
                binary,
                "-A",
                chain,
                "-j",
                "RETURN",
            ]
        )

        commands.append(
            [
                binary,
                "-D",
                self.FORWARD_RULE_CHAIN,
                "-j",
                chain,
            ]
        )

        commands.append(
            [
                binary,
                "-I",
                self.FORWARD_RULE_CHAIN,
                "1",
                "-j",
                chain,
            ]
        )

        return commands

    def apply(
        self,
        policy: VpnTrafficPolicy,
    ) -> None:
        for command in self.build_commands(policy):
            result = self._executor.run(command)

            if result.returncode == 0:
                continue

            if self._is_missing_chain_error(command, result.stderr):
                continue

            if self._is_missing_jump_error(command, result.stderr):
                continue

            raise RuntimeError(
                "OpenWrt firewall command failed: "
                f"{command!r}; "
                f"returncode={result.returncode}; "
                f"stderr={result.stderr!r}"
            )

    @staticmethod
    def _is_missing_chain_error(
        command: list[str],
        stderr: str,
    ) -> bool:
        return (
            len(command) >= 3
            and command[1] == "-N"
            and "Chain already exists" in stderr
        )

    @staticmethod
    def _is_missing_jump_error(
        command: list[str],
        stderr: str,
    ) -> bool:
        if (
            len(command) < 5
            or command[1] != "-D"
            or command[2] != OpenWrtFirewallExecutor.FORWARD_RULE_CHAIN
        ):
            return False

        return "Bad rule" in stderr or "No chain/target/match by that name" in stderr
