from __future__ import annotations

import re
from dataclasses import dataclass
from ipaddress import ip_address

from backend.ports.remote_command_executor import RemoteCommandExecutor


@dataclass(frozen=True, slots=True)
class SmartRoutingDomainDiagnosticResult:
    domain: str
    dns_ipv4_addresses: tuple[str, ...]
    present_ipv4_addresses: tuple[str, ...]
    missing_ipv4_addresses: tuple[str, ...]
    stale_ipv4_addresses: tuple[str, ...]
    route_results: tuple[str, ...]
    healthy: bool
    reason: str | None = None
    direct_ipset_readable: bool = False
    dnsmasq_mapping_present: bool = False
    marking_rule_present: bool = False
    policy_rule_present: bool = False
    forward_chain_attached: bool = False
    direct_forward_rule_present: bool = False
    nat_chain_attached: bool = False
    nat_masquerade_rule_present: bool = False


class SmartRoutingDomainDiagnosticService:
    # Read-only domain-to-DIRECT diagnostic. This service never mutates runtime state.

    DIRECT_IPSET = "MAXVPN_DIRECT"
    ROUTING_TABLE = 200
    FWMARK = 0x64
    WAN_INTERFACE = "eth1"
    DNSMASQ_RUNTIME_DIR = "/var/etc"

    def __init__(
        self,
        executor: RemoteCommandExecutor,
        *,
        dns_server: str = "127.0.0.1",
    ) -> None:
        self._executor = executor
        self._dns_server = dns_server

    def check(self, domain: str) -> SmartRoutingDomainDiagnosticResult:
        normalized_domain = self._normalize_domain(domain)
        dns_ipv4 = self._resolve_ipv4(normalized_domain)
        runtime_ipv4, direct_ipset_readable = self._read_direct_ipset()

        present = tuple(address for address in dns_ipv4 if address in runtime_ipv4)
        missing = tuple(address for address in dns_ipv4 if address not in runtime_ipv4)
        # A shared IPSet cannot identify stale addresses from one domain alone.
        stale: tuple[str, ...] = ()

        dnsmasq_mapping_present = self._has_dnsmasq_direct_mapping(normalized_domain)
        marking_rule_present = self._command_succeeds(
            [
                "iptables",
                "-t",
                "mangle",
                "-C",
                "PREROUTING",
                "-i",
                "br-lan",
                "-m",
                "set",
                "--match-set",
                self.DIRECT_IPSET,
                "dst",
                "-j",
                "MARK",
                "--set-xmark",
                "0x64/0xff",
            ]
        )
        policy_rule_present = self._has_direct_policy_rule()
        forward_chain_attached = self._command_succeeds(
            [
                "iptables",
                "-C",
                "forwarding_rule",
                "-j",
                "MAXVPN_LAN_FORWARD",
            ]
        )
        direct_forward_rule_present = self._command_succeeds(
            [
                "iptables",
                "-C",
                "MAXVPN_LAN_FORWARD",
                "-i",
                "br-lan",
                "-o",
                self.WAN_INTERFACE,
                "-m",
                "mark",
                "--mark",
                "0x64/0xff",
                "-j",
                "ACCEPT",
            ]
        )
        nat_chain_attached = self._command_succeeds(
            [
                "iptables",
                "-t",
                "nat",
                "-C",
                "POSTROUTING",
                "-j",
                "MAXVPN_DIRECT_NAT",
            ]
        )
        nat_masquerade_rule_present = self._command_succeeds(
            [
                "iptables",
                "-t",
                "nat",
                "-C",
                "MAXVPN_DIRECT_NAT",
                "-o",
                self.WAN_INTERFACE,
                "-m",
                "mark",
                "--mark",
                "0x64/0xff",
                "-j",
                "MASQUERADE",
            ]
        )

        route_results = tuple(self._check_marked_route(address) for address in present)
        failed_routes = [item for item in route_results if not item.endswith(" OK")]

        checks_ok = all(
            (
                direct_ipset_readable,
                dnsmasq_mapping_present,
                marking_rule_present,
                policy_rule_present,
                forward_chain_attached,
                direct_forward_rule_present,
                nat_chain_attached,
                nat_masquerade_rule_present,
            )
        )
        healthy = bool(dns_ipv4) and not missing and not failed_routes and checks_ok

        reason: str | None = None
        if not dns_ipv4:
            reason = "domain_dns_ipv4_not_found"
        elif not direct_ipset_readable:
            reason = "direct_ipset_unavailable_or_incomplete"
        elif not dnsmasq_mapping_present:
            reason = "dnsmasq_direct_mapping_missing"
        elif missing:
            reason = "dns_ipv4_missing_from_direct_ipset: " + ",".join(missing)
        elif not marking_rule_present:
            reason = "direct_marking_rule_missing"
        elif not policy_rule_present:
            reason = "direct_policy_rule_missing"
        elif not forward_chain_attached:
            reason = "direct_forward_chain_not_attached"
        elif not direct_forward_rule_present:
            reason = "direct_forward_accept_rule_missing"
        elif not nat_chain_attached:
            reason = "direct_nat_chain_not_attached"
        elif not nat_masquerade_rule_present:
            reason = "direct_nat_masquerade_rule_missing"
        elif failed_routes:
            reason = "marked_route_verification_failed"

        return SmartRoutingDomainDiagnosticResult(
            domain=normalized_domain,
            dns_ipv4_addresses=dns_ipv4,
            present_ipv4_addresses=present,
            missing_ipv4_addresses=missing,
            stale_ipv4_addresses=stale,
            route_results=route_results,
            healthy=healthy,
            reason=reason,
            direct_ipset_readable=direct_ipset_readable,
            dnsmasq_mapping_present=dnsmasq_mapping_present,
            marking_rule_present=marking_rule_present,
            policy_rule_present=policy_rule_present,
            forward_chain_attached=forward_chain_attached,
            direct_forward_rule_present=direct_forward_rule_present,
            nat_chain_attached=nat_chain_attached,
            nat_masquerade_rule_present=nat_masquerade_rule_present,
        )

    def _resolve_ipv4(self, domain: str) -> tuple[str, ...]:
        result = self._executor.run(["nslookup", domain, self._dns_server])
        if result.returncode != 0:
            return ()

        addresses: list[str] = []
        for line in result.stdout.splitlines():
            match = re.match(r"^\s*Address(?:\s+\d+)?\s*:\s*(\S+)", line)
            if not match:
                continue

            value = match.group(1)
            if "#" in value:
                continue
            try:
                address = ip_address(value)
            except ValueError:
                continue
            if address.version == 4 and str(address) != self._dns_server:
                addresses.append(str(address))
        return tuple(dict.fromkeys(addresses))

    def _read_direct_ipset(self) -> tuple[set[str], bool]:
        result = self._run(["ipset", "list", self.DIRECT_IPSET], check=False)
        if result.returncode != 0:
            return set(), False

        addresses: set[str] = set()
        in_members = False
        found_members = False
        for line in (result.stdout or "").splitlines():
            stripped = line.strip()
            if stripped == "Members:":
                in_members = True
                found_members = True
                continue
            if not in_members or not stripped:
                continue
            # Timed ipset members are rendered as:
            # "<IPv4 address> timeout <remaining seconds>".
            match = re.fullmatch(r"(\S+)(?:\s+timeout\s+\d+)?", stripped)
            if match is None:
                continue
            try:
                address = ip_address(match.group(1))
            except ValueError:
                continue
            if address.version == 4:
                addresses.add(str(address))
        return addresses, found_members

    def _has_dnsmasq_direct_mapping(self, domain: str) -> bool:
        # Inspect generated dnsmasq configuration, not only UCI intent.
        # A parent-domain ipset mapping also covers its subdomains.
        result = self._run(
            ["grep", "-R", "-F", "MAXVPN_DIRECT", self.DNSMASQ_RUNTIME_DIR],
            check=False,
        )
        if result.returncode != 0:
            return False

        for raw_line in (result.stdout or "").splitlines():
            line = raw_line.split(":", 1)[-1].strip()
            if not line.startswith("ipset="):
                continue
            value = line[len("ipset=") :]
            if not value.startswith("/"):
                continue
            parts = [part for part in value.strip("/").split("/") if part]
            if len(parts) < 2 or parts[-1] != self.DIRECT_IPSET:
                continue
            for configured_domain in parts[:-1]:
                candidate = configured_domain.lower().rstrip(".")
                if domain == candidate or domain.endswith("." + candidate):
                    return True
        return False

    def _has_direct_policy_rule(self) -> bool:
        result = self._run(["ip", "-4", "rule", "show"], check=False)
        if result.returncode != 0:
            return False
        return bool(
            re.search(
                r"\bfwmark\s+0x64/0xff\s+lookup\s+200\b",
                result.stdout or "",
            )
        )

    def _command_succeeds(self, command: list[str]) -> bool:
        return self._run(command, check=False).returncode == 0

    def _check_marked_route(self, address: str) -> str:
        result = self._run(
            ["ip", "-4", "route", "get", address, "mark", f"0x{self.FWMARK:x}"],
            check=False,
        )
        output = (result.stdout or "").strip()
        if (
            result.returncode == 0
            and f"table {self.ROUTING_TABLE}" in output
            and f"mark 0x{self.FWMARK:x}" in output
            and f"dev {self.WAN_INTERFACE}" in output
        ):
            return f"{address} -> {output} OK"
        return f"{address} -> {output or 'route lookup failed'} FAIL"

    def _run(self, command: list[str], *, check: bool = True):
        result = self._executor.run(command)
        if check and result.returncode != 0:
            raise RuntimeError(
                "smart_routing_domain_diagnostic_command_failed: "
                f"command={command!r}; returncode={result.returncode}; "
                f"stderr={result.stderr!r}",
            )
        return result

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        value = domain.strip().lower().rstrip(".")
        if value.startswith("*."):
            value = value[2:]
        if not value or "." not in value:
            raise ValueError("domain must contain at least two labels")
        return value
