from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Iterable

from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.ports.remote_command_executor import RemoteCommandExecutor
from backend.services.domain_routing_runtime_compiler import (
    DomainRoutingRuntimeCompiler,
)


@dataclass(frozen=True, slots=True)
class OpenWrtDnsmasqRoutingResult:
    healthy: bool
    dnsmasq_section_exists: bool
    direct_ipset_mapping_count: int
    expected_domain_count: int
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class OpenWrtDnsmasqRoutingSnapshot:
    section_exists: bool
    domains: tuple[str, ...]


class OpenWrtDnsmasqRoutingService:
    """
    Manages MaxVPN DOMAIN -> ipset mappings through an OpenWrt
    `config ipset` section.

    Brume 3 / GL.iNet dnsmasq integration expects:

        config ipset
            list name 'MAXVPN_DIRECT'
            list domain 'example.com'

    which is rendered by /etc/init.d/dnsmasq as:

        ipset=/example.com/MAXVPN_DIRECT
    """

    UCI_CONFIG = "dhcp"
    IPSET_SECTION_TYPE = "ipset"
    DIRECT_IPSET = "MAXVPN_DIRECT"
    DNSMASQ_CONF_GLOB = "/var/etc/dnsmasq.conf*"

    def __init__(
        self,
        executor: RemoteCommandExecutor,
        *,
        compiler: DomainRoutingRuntimeCompiler | None = None,
    ) -> None:
        self._executor = executor
        self._compiler = compiler or DomainRoutingRuntimeCompiler()

    def capture_snapshot(self) -> OpenWrtDnsmasqRoutingSnapshot:
        result = self._run(
            [
                "uci",
                "show",
                self.UCI_CONFIG,
            ],
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "dnsmasq_snapshot_failed: uci_unavailable",
            )

        section = self._find_direct_ipset_section(result.stdout)

        if section is None:
            return OpenWrtDnsmasqRoutingSnapshot(
                section_exists=False,
                domains=(),
            )

        domains = tuple(
            sorted(
                self._extract_domains_from_uci(
                    result.stdout,
                    section,
                ),
            ),
        )

        return OpenWrtDnsmasqRoutingSnapshot(
            section_exists=True,
            domains=domains,
        )

    def restore_snapshot(
        self,
        snapshot: OpenWrtDnsmasqRoutingSnapshot,
    ) -> None:
        commands = (
            self.build_apply_commands(snapshot.domains)
            if snapshot.section_exists
            else self.build_remove_commands()
        )

        for command in commands:
            self._run_checked(command)

    def apply(
        self,
        policy: TrafficRoutingPolicy,
    ) -> None:
        domains = self._extract_direct_domain_mappings(policy)

        for command in self.build_apply_commands(domains):
            self._run_checked(command)

    def preview(
        self,
        policy: TrafficRoutingPolicy,
    ) -> list[list[str]]:
        """Build the OpenWrt dnsmasq commands without executing them."""
        domains = self._extract_direct_domain_mappings(policy)
        return self.build_apply_commands(domains)

    def remove(self) -> None:
        for command in self.build_remove_commands():
            self._run_checked(command)

    def verify(
        self,
        expected_domains: Iterable[str] = (),
    ) -> OpenWrtDnsmasqRoutingResult:
        expected = tuple(self._normalize_domain(domain) for domain in expected_domains)

        uci_result = self._run(
            [
                "uci",
                "show",
                self.UCI_CONFIG,
            ],
            check=False,
        )

        if uci_result.returncode != 0:
            return OpenWrtDnsmasqRoutingResult(
                healthy=False,
                dnsmasq_section_exists=False,
                direct_ipset_mapping_count=0,
                expected_domain_count=len(expected),
                reason="dnsmasq_uci_unavailable",
            )

        section = self._find_direct_ipset_section(
            uci_result.stdout,
        )

        if section is None:
            return OpenWrtDnsmasqRoutingResult(
                healthy=False,
                dnsmasq_section_exists=False,
                direct_ipset_mapping_count=0,
                expected_domain_count=len(expected),
                reason="maxvpn_ipset_section_missing",
            )

        domains = self._extract_domains_from_uci(
            uci_result.stdout,
            section,
        )

        missing = [domain for domain in expected if domain not in domains]

        rendered_result = self._run(
            [
                "sh",
                "-c",
                (f"grep -Rh -F 'ipset=/' {self.DNSMASQ_CONF_GLOB} 2>/dev/null || true"),
            ],
            check=False,
        )

        rendered_domains = self._parse_rendered_domains(
            rendered_result.stdout,
        )

        missing_rendered = [
            domain for domain in expected if domain not in rendered_domains
        ]

        failed_checks: list[str] = []

        if missing:
            failed_checks.append(
                "missing_uci_domains=" + ",".join(missing),
            )

        if missing_rendered:
            failed_checks.append(
                "missing_rendered_domains=" + ",".join(missing_rendered),
            )

        return OpenWrtDnsmasqRoutingResult(
            healthy=not failed_checks,
            dnsmasq_section_exists=True,
            direct_ipset_mapping_count=len(domains),
            expected_domain_count=len(expected),
            reason=(
                None
                if not failed_checks
                else (
                    "dnsmasq_routing_verification_failed: " + ", ".join(failed_checks)
                )
            ),
        )

    def build_apply_commands(
        self,
        mappings: Iterable[str],
    ) -> list[list[str]]:
        domains = tuple(self._normalize_domain(domain) for domain in mappings)

        domains_shell = " ".join(self._shell_quote(domain) for domain in domains)

        script = (
            "set -u; "
            "uci set dhcp.@dnsmasq[0].logqueries='1'; "
            "uci set dhcp.@dnsmasq[0].logfacility='/tmp/maxvpn-dns-events.log'; "
            "section=''; "
            "for candidate in $(uci show dhcp 2>/dev/null "
            "| sed -n "
            '"s/^\\(dhcp\\.[^.]*\\)=ipset$/\\1/p"'
            "); do "
            'name=$(uci -q get "$candidate.name" 2>/dev/null || true); '
            f'if [ "$name" = "{self.DIRECT_IPSET}" ]; then '
            'section="$candidate"; '
            "break; "
            "fi; "
            "done; "
            'if [ -z "$section" ]; then '
            f"new_section=$(uci add {self.UCI_CONFIG} "
            f"{self.IPSET_SECTION_TYPE}); "
            f'section="{self.UCI_CONFIG}.$new_section"; '
            "fi; "
            'uci -q delete "$section.name" 2>/dev/null || true; '
            'uci delete "$section.domain" 2>/dev/null || true; '
            f'uci add_list "$section.name={self.DIRECT_IPSET}"; '
        )

        if domains_shell:
            script += (
                "for domain in "
                f"{domains_shell}; do "
                'uci add_list "$section.domain=$domain"; '
                "done; "
            )

        script += "uci commit dhcp; /etc/init.d/dnsmasq restart"

        return [
            [
                "sh",
                "-c",
                script,
            ],
        ]

    def build_remove_commands(self) -> list[list[str]]:
        script = (
            "set -u; "
            "uci -q delete dhcp.@dnsmasq[0].logqueries 2>/dev/null || true; "
            "uci -q delete dhcp.@dnsmasq[0].logfacility 2>/dev/null || true; "
            "rm -f /tmp/maxvpn-dns-events.log; "
            "for candidate in $(uci show dhcp 2>/dev/null "
            "| sed -n "
            '"s/^\\(dhcp\\.[^.]*\\)=ipset$/\\1/p"'
            "); do "
            'name=$(uci -q get "$candidate.name" 2>/dev/null || true); '
            f'if [ "$name" = "{self.DIRECT_IPSET}" ]; then '
            'uci delete "$candidate"; '
            "break; "
            "fi; "
            "done; "
            "uci commit dhcp; "
            "/etc/init.d/dnsmasq restart"
        )

        return [
            [
                "sh",
                "-c",
                script,
            ],
        ]

    def _extract_direct_domain_mappings(
        self,
        policy: TrafficRoutingPolicy,
    ) -> tuple[str, ...]:
        return self._compiler.compile(policy).direct_domains

    def _find_direct_ipset_section(
        self,
        uci_output: str,
    ) -> str | None:
        sections: list[str] = []

        for line in uci_output.splitlines():
            if not line.startswith("dhcp."):
                continue

            if not line.endswith("=ipset"):
                continue

            section = line.split("=", 1)[0]
            sections.append(section)

        for section in sections:
            prefix = f"{section}.name="
            for line in uci_output.splitlines():
                if not line.startswith(prefix):
                    continue

                value = line.split("=", 1)[1].strip()

                if value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]

                if value == self.DIRECT_IPSET:
                    return section

        return None

    def _extract_domains_from_uci(
        self,
        uci_output: str,
        section: str,
    ) -> set[str]:
        prefix = f"{section}.domain="

        domains: set[str] = set()

        for line in uci_output.splitlines():
            if not line.startswith(prefix):
                continue

            value = line.split("=", 1)[1].strip()

            for domain in shlex.split(value):
                domains.add(
                    self._normalize_domain(domain),
                )

        return domains

    def _parse_rendered_domains(
        self,
        output: str,
    ) -> set[str]:
        domains: set[str] = set()

        marker = "ipset=/"

        for line in output.splitlines():
            position = line.find(marker)

            if position < 0:
                continue

            rendered = line[position + len(marker) :].strip()

            prefix, separator, ipset_name = rendered.rpartition("/")

            if not separator or ipset_name != self.DIRECT_IPSET:
                continue

            for domain in prefix.split("/"):
                if not domain:
                    continue

                domains.add(
                    self._normalize_domain(domain),
                )

        return domains

    def _run(
        self,
        command: list[str],
        *,
        check: bool = True,
    ):
        result = self._executor.run(command)

        if check and result.returncode != 0:
            raise RuntimeError(
                "OpenWrt dnsmasq routing command failed: "
                f"{command!r}; "
                f"returncode={result.returncode}; "
                f"stderr={result.stderr!r}",
            )

        return result

    def _run_checked(
        self,
        command: list[str],
    ) -> None:
        self._run(command)

    @staticmethod
    def _shell_quote(value: str) -> str:
        escaped = value.replace("'", "'\"'\"'")
        return f"'{escaped}'"

    @staticmethod
    def _normalize_domain(
        domain: str,
    ) -> str:
        value = domain.strip().lower().rstrip(".")

        if value.startswith("*."):
            value = value[2:]

        if not value:
            raise ValueError(
                "domain must not be empty",
            )

        labels = value.split(".")

        if len(labels) < 2:
            raise ValueError(
                "domain must contain at least two labels",
            )

        if any(not label for label in labels):
            raise ValueError(
                "domain contains an empty label",
            )

        return value
