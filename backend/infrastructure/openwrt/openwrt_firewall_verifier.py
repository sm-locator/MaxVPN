from __future__ import annotations

from dataclasses import dataclass

from backend.ports.remote_command_executor import RemoteCommandExecutor


@dataclass(frozen=True, slots=True)
class OpenWrtFirewallVerificationResult:
    healthy: bool
    ipv4_chain_exists: bool
    ipv6_chain_exists: bool
    ipv4_jump_count: int
    ipv6_jump_count: int
    ipv4_vpn_accept_rule: bool
    ipv4_wan_drop_rule: bool
    ipv6_vpn_accept_rule: bool
    ipv6_wan_drop_rule: bool
    reason: str | None = None


class OpenWrtFirewallVerifier:
    """
    Verifies the actual runtime state of the MaxVPN firewall policy.
    """

    IPV4_CHAIN = "MAXVPN_LAN_FORWARD"
    IPV6_CHAIN = "MAXVPN_LAN6_FORWARD"
    FORWARD_RULE_CHAIN = "forwarding_rule"

    def __init__(
        self,
        executor: RemoteCommandExecutor,
    ) -> None:
        self._executor = executor

    def verify(self) -> OpenWrtFirewallVerificationResult:
        ipv4_chain = self._run(
            [
                "iptables",
                "-S",
                self.IPV4_CHAIN,
            ]
        )

        ipv4_forwarding = self._run(
            [
                "iptables",
                "-S",
                self.FORWARD_RULE_CHAIN,
            ]
        )

        ipv6_chain = self._run(
            [
                "ip6tables",
                "-S",
                self.IPV6_CHAIN,
            ]
        )

        ipv6_forwarding = self._run(
            [
                "ip6tables",
                "-S",
                self.FORWARD_RULE_CHAIN,
            ]
        )

        return self._evaluate(
            ipv4_chain=ipv4_chain,
            ipv4_forwarding=ipv4_forwarding,
            ipv6_chain=ipv6_chain,
            ipv6_forwarding=ipv6_forwarding,
        )

    def _run(
        self,
        command: list[str],
    ) -> tuple[int, str, str]:
        result = self._executor.run(command)

        return (
            result.returncode,
            result.stdout,
            result.stderr,
        )

    def _evaluate(
        self,
        *,
        ipv4_chain: tuple[int, str, str],
        ipv4_forwarding: tuple[int, str, str],
        ipv6_chain: tuple[int, str, str],
        ipv6_forwarding: tuple[int, str, str],
    ) -> OpenWrtFirewallVerificationResult:
        ipv4_chain_text = ipv4_chain[1]
        ipv4_forwarding_text = ipv4_forwarding[1]

        ipv6_chain_text = ipv6_chain[1]
        ipv6_forwarding_text = ipv6_forwarding[1]

        ipv4_chain_exists = ipv4_chain[0] == 0
        ipv6_chain_exists = ipv6_chain[0] == 0

        ipv4_jump_count = self._count_jump(
            ipv4_forwarding_text,
            self.IPV4_CHAIN,
        )

        ipv6_jump_count = self._count_jump(
            ipv6_forwarding_text,
            self.IPV6_CHAIN,
        )

        ipv4_vpn_accept_rule = self._contains_rule(
            ipv4_chain_text,
            self.IPV4_CHAIN,
            "br-lan",
            "WireGuard",
            "ACCEPT",
        )

        ipv4_wan_drop_rule = self._contains_rule(
            ipv4_chain_text,
            self.IPV4_CHAIN,
            "br-lan",
            "eth1",
            "DROP",
        )

        ipv6_vpn_accept_rule = self._contains_rule(
            ipv6_chain_text,
            self.IPV6_CHAIN,
            "br-lan",
            "WireGuard",
            "ACCEPT",
        )

        ipv6_wan_drop_rule = self._contains_rule(
            ipv6_chain_text,
            self.IPV6_CHAIN,
            "br-lan",
            "eth1",
            "DROP",
        )

        checks = {
            "ipv4_chain_exists": ipv4_chain_exists,
            "ipv6_chain_exists": ipv6_chain_exists,
            "ipv4_single_jump": ipv4_jump_count == 1,
            "ipv6_single_jump": ipv6_jump_count == 1,
            "ipv4_vpn_accept": ipv4_vpn_accept_rule,
            "ipv4_wan_drop": ipv4_wan_drop_rule,
            "ipv6_vpn_accept": ipv6_vpn_accept_rule,
            "ipv6_wan_drop": ipv6_wan_drop_rule,
        }

        failed_checks = [name for name, passed in checks.items() if not passed]

        return OpenWrtFirewallVerificationResult(
            healthy=not failed_checks,
            ipv4_chain_exists=ipv4_chain_exists,
            ipv6_chain_exists=ipv6_chain_exists,
            ipv4_jump_count=ipv4_jump_count,
            ipv6_jump_count=ipv6_jump_count,
            ipv4_vpn_accept_rule=ipv4_vpn_accept_rule,
            ipv4_wan_drop_rule=ipv4_wan_drop_rule,
            ipv6_vpn_accept_rule=ipv6_vpn_accept_rule,
            ipv6_wan_drop_rule=ipv6_wan_drop_rule,
            reason=(
                None
                if not failed_checks
                else "firewall_verification_failed: " + ", ".join(failed_checks)
            ),
        )

    @staticmethod
    def _count_jump(
        forwarding_rules: str,
        chain: str,
    ) -> int:
        target = f"-j {chain}"

        return sum(1 for line in forwarding_rules.splitlines() if target in line)

    @staticmethod
    def _contains_rule(
        chain_rules: str,
        chain: str,
        input_interface: str,
        output_interface: str,
        target: str,
    ) -> bool:
        expected = f"-A {chain} -i {input_interface} -o {output_interface} -j {target}"

        return expected in chain_rules
