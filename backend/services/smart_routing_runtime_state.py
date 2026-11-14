from __future__ import annotations

import shlex
from dataclasses import dataclass
from ipaddress import ip_address

from backend.ports.remote_command_executor import RemoteCommandExecutor


@dataclass(frozen=True, slots=True)
class SmartRoutingRuntimeState:
    direct_ipv4_addresses: tuple[str, ...]
    static_direct_ipv4_addresses: tuple[str, ...]
    direct_domains: tuple[str, ...]
    rendered_domains: tuple[str, ...]
    policy_rules: tuple[str, ...]
    routing_table_200: tuple[str, ...]
    direct_ipv6_addresses: tuple[str, ...] = ()


class SmartRoutingRuntimeStateCollector:
    """
    Read-only collector of the current MaxVPN Smart Routing state.

    No command performed by this class modifies the router.
    """

    DIRECT_IPSET = "MAXVPN_DIRECT"
    STATIC_DIRECT_IPSET = "MAXVPN_DIRECT_STATIC"
    ROUTING_TABLE = 200

    def __init__(self, executor: RemoteCommandExecutor) -> None:
        self._executor = executor

    def collect(self) -> SmartRoutingRuntimeState:
        ipset_result = self._run(
            ["ipset", "list", self.DIRECT_IPSET],
            check=False,
        )

        static_ipset_result = self._run(
            ["ipset", "list", self.STATIC_DIRECT_IPSET],
            check=False,
        )

        ipv6_ipset_result = self._run(
            ["ipset", "list", "MAXVPN_DIRECT6"],
            check=False,
        )

        uci_result = self._run(
            ["uci", "show", "dhcp"],
            check=False,
        )

        rendered_result = self._run(
            [
                "sh",
                "-c",
                "set -- /var/etc/dnsmasq.conf*; "
                "found=0; "
                'for path do [ -f "$path" ] && found=1; done; '
                '[ "$found" -eq 1 ] || { '
                "echo 'smart_routing_dnsmasq_config_missing' >&2; exit 2; }; "
                "grep -Rni 'ipset=/.*\\/MAXVPN_DIRECT$' "
                "/var/etc/dnsmasq.conf* 2>/dev/null || true",
            ],
            check=False,
        )

        rules_result = self._run(
            ["ip", "rule", "show"],
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

        # Empty output is a valid state, but a failed read is not. In
        # particular, do not interpret a failed UCI/iptables read as an empty
        # DIRECT configuration and then delete live DNS-derived ipset entries.
        for result, command_name in (
            (ipset_result, self.DIRECT_IPSET),
            (static_ipset_result, self.STATIC_DIRECT_IPSET),
            (uci_result, "uci show dhcp"),
            (rendered_result, "rendered dnsmasq config"),
        ):
            if result.returncode != 0:
                raise RuntimeError(
                    "smart_routing_runtime_state_read_failed: "
                    f"source={command_name}; "
                    f"returncode={result.returncode}; "
                    f"stderr={result.stderr!r}",
                )

        dns_direct_ipv4 = self._parse_ipset(ipset_result.stdout)
        static_direct_ipv4 = self._parse_ipset(
            static_ipset_result.stdout,
            family=4,
        )
        direct_ipv6 = self._parse_ipset(
            ipv6_ipset_result.stdout,
            family=6,
        )

        return SmartRoutingRuntimeState(
            direct_ipv4_addresses=tuple(
                sorted(set(dns_direct_ipv4) | set(static_direct_ipv4)),
            ),
            static_direct_ipv4_addresses=static_direct_ipv4,
            direct_domains=self._parse_uci_domains(uci_result.stdout),
            direct_ipv6_addresses=direct_ipv6,
            rendered_domains=self._parse_rendered_domains(
                rendered_result.stdout,
            ),
            policy_rules=tuple(
                line.strip()
                for line in (rules_result.stdout or "").splitlines()
                if line.strip()
            ),
            routing_table_200=tuple(
                line.strip()
                for line in (table_result.stdout or "").splitlines()
                if line.strip()
            ),
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
                "smart_routing_runtime_state_command_failed: "
                f"command={command!r}; "
                f"returncode={result.returncode}; "
                f"stderr={result.stderr!r}",
            )

        return result

    @classmethod
    def _parse_ipset(
        cls,
        output: str,
        *,
        family: int = 4,
    ) -> tuple[str, ...]:
        members: list[str] = []

        in_members = False

        for line in (output or "").splitlines():
            stripped = line.strip()

            if stripped == "Members:":
                in_members = True
                continue

            if not in_members or not stripped:
                continue

            try:
                address = ip_address(stripped)
            except ValueError:
                continue

            if address.version == family:
                members.append(str(address))

        return tuple(sorted(set(members)))

    @classmethod
    def _parse_uci_domains(cls, output: str) -> tuple[str, ...]:
        domains: set[str] = set()
        values: dict[str, dict[str, list[str]]] = {}

        for line in (output or "").splitlines():
            stripped = line.strip()

            if not stripped.startswith("dhcp.") or "=" not in stripped:
                continue

            key, raw_value = stripped.split("=", 1)

            if "." not in key:
                continue

            section, option = key.rsplit(".", 1)

            try:
                parsed_values = shlex.split(raw_value.strip())
            except ValueError:
                continue

            if not parsed_values:
                continue

            values.setdefault(section, {}).setdefault(option, []).extend(
                parsed_values,
            )

        for section, options in values.items():
            names = options.get("name", [])

            if cls.DIRECT_IPSET not in names:
                continue

            for domain in options.get("domain", []):
                normalized = domain.lower().rstrip(".")

                if normalized:
                    domains.add(normalized)

        return tuple(sorted(domains))

    @staticmethod
    def _parse_rendered_domains(output: str) -> tuple[str, ...]:
        domains: set[str] = set()

        for line in (output or "").splitlines():
            marker = "ipset=/"

            if marker not in line:
                continue

            value = line.split(marker, 1)[1]

            marker = "/MAXVPN_DIRECT"
            if not value.endswith(marker):
                continue

            domain_path = value[: -len(marker)].strip()

            for domain in domain_path.split("/"):
                domain = domain.strip().lower().rstrip(".")

                if domain:
                    domains.add(domain)

        return tuple(sorted(domains))
