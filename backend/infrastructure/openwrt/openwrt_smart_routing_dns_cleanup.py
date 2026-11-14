from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address

from backend.ports.remote_command_executor import RemoteCommandExecutor


class OpenWrtSmartRoutingDnsCleanup:
    DIRECT_IPSET = "MAXVPN_DIRECT"
    DIRECT_IPSET_V6 = "MAXVPN_DIRECT6"

    def __init__(self, executor: RemoteCommandExecutor) -> None:
        self._executor = executor

    def add_addresses(
        self,
        ipv4_addresses: tuple[str, ...],
    ) -> tuple[str, ...]:
        added: list[str] = []

        for address in ipv4_addresses:
            normalized = str(IPv4Address(address))

            result = self._executor.run(
                [
                    "ipset",
                    "add",
                    self.DIRECT_IPSET,
                    normalized,
                    "-exist",
                ],
            )

            if result.returncode != 0:
                raise RuntimeError(
                    "smart_routing_dns_add_failed: "
                    f"ip={normalized}; "
                    f"returncode={result.returncode}; "
                    f"stderr={result.stderr!r}",
                )

            added.append(normalized)

        return tuple(added)

    def add_ipv6_addresses(
        self,
        ipv6_addresses: tuple[str, ...],
    ) -> tuple[str, ...]:
        added: list[str] = []

        for address in ipv6_addresses:
            normalized = str(IPv6Address(address))

            result = self._executor.run(
                [
                    "ipset",
                    "add",
                    self.DIRECT_IPSET_V6,
                    normalized,
                    "-exist",
                ],
            )

            if result.returncode != 0:
                raise RuntimeError(
                    "smart_routing_dns_add_ipv6_failed: "
                    f"ip={normalized}; "
                    f"returncode={result.returncode}; "
                    f"stderr={result.stderr!r}",
                )

            added.append(normalized)

        return tuple(added)

    def remove_stale(
        self,
        ipv4_addresses: tuple[str, ...],
    ) -> tuple[str, ...]:
        removed: list[str] = []

        for address in ipv4_addresses:
            normalized = str(IPv4Address(address))

            result = self._executor.run(
                [
                    "ipset",
                    "del",
                    self.DIRECT_IPSET,
                    normalized,
                ],
            )

            if result.returncode not in (0, 1):
                raise RuntimeError(
                    "smart_routing_dns_cleanup_failed: "
                    f"ip={normalized}; "
                    f"returncode={result.returncode}; "
                    f"stderr={result.stderr!r}",
                )

            if result.returncode == 0:
                removed.append(normalized)

        return tuple(removed)

    def remove_stale_ipv6(
        self,
        ipv6_addresses: tuple[str, ...],
    ) -> tuple[str, ...]:
        removed: list[str] = []

        for address in ipv6_addresses:
            normalized = str(IPv6Address(address))

            result = self._executor.run(
                [
                    "ipset",
                    "del",
                    self.DIRECT_IPSET_V6,
                    normalized,
                ],
            )

            if result.returncode not in (0, 1):
                raise RuntimeError(
                    "smart_routing_dns_cleanup_ipv6_failed: "
                    f"ip={normalized}; "
                    f"returncode={result.returncode}; "
                    f"stderr={result.stderr!r}",
                )

            if result.returncode == 0:
                removed.append(normalized)

        return tuple(removed)
