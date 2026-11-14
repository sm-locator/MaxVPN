from __future__ import annotations

import re
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address
from time import monotonic


@dataclass(frozen=True, slots=True)
class SmartRoutingDnsResponse:
    process_id: int
    transaction_id: str
    domain: str
    ipv4_addresses: tuple[str, ...]
    ipv6_addresses: tuple[str, ...] = ()


@dataclass(slots=True)
class _PendingTransaction:
    process_id: int
    transaction_id: str
    domain: str
    ipv4_addresses: set[str]
    ipv6_addresses: set[str]
    last_activity: float


@dataclass(slots=True)
class _AmbiguousTransaction:
    domains: set[str]
    last_activity: float


class SmartRoutingDnsResponseObserver:
    LOG_PATH = "/tmp/maxvpn-dns-events.log"
    MAX_PENDING = 4096
    PENDING_TTL_SECONDS = 120.0

    _QUERY = re.compile(
        r"""
        ^
        (?P<process_id>\d+)
        :
        (?P<transaction_id>\d+)
        \s+
        \S+/\S+
        \s+
        query\[(?P<record_type>A|AAAA)\]
        \s+
        (?P<domain>\S+)
        \s+
        from
        \s+
        \S+
        $
        """,
        re.VERBOSE,
    )

    _REPLY_IPV4 = re.compile(
        r"""
        ^
        (?P<process_id>\d+)
        :
        (?P<transaction_id>\d+)
        \s+
        \S+/\S+
        \s+
        reply
        \s+
        (?P<domain>\S+)
        \s+
        is
        \s+
        (?P<ipv4>\d+\.\d+\.\d+\.\d+)
        $
        """,
        re.VERBOSE,
    )

    _REPLY = re.compile(
        r"""
        ^
        (?P<process_id>\d+)
        :
        (?P<transaction_id>\d+)
        \s+
        \S+/\S+
        \s+
        reply
        \s+
        (?P<domain>\S+)
        \s+
        is
        \s+
        (?P<value>\S+)
        $
        """,
        re.VERBOSE,
    )

    def __init__(self) -> None:
        # _AmbiguousTransaction keeps colliding transaction IDs blocked until expiry.
        self._pending: dict[
            tuple[str, str],
            _PendingTransaction | _AmbiguousTransaction,
        ] = {}

    def reset(self) -> None:
        """Discard partial DNS transactions after the source log is reset."""
        self._pending.clear()

    def prune_pending(
        self,
        direct_domains: tuple[str, ...],
        *,
        now: float | None = None,
    ) -> int:
        """Remove expired transactions and entries outside the DIRECT policy."""
        allowed_domains = {
            self._normalize_domain(domain)
            for domain in direct_domains
            if self._normalize_domain(domain)
        }
        current_time = monotonic() if now is None else now
        stale_keys: list[tuple[str, str]] = []

        for transaction_key, transaction in self._pending.items():
            # Compare absolute deadlines. Subtracting two monotonic float values
            # can round an exact TTL boundary slightly below the threshold.
            if current_time >= (transaction.last_activity + self.PENDING_TTL_SECONDS):
                stale_keys.append(transaction_key)
                continue

            if isinstance(transaction, _PendingTransaction):
                remains_direct = self._matches_direct_domain(
                    transaction.domain,
                    allowed_domains,
                )
            else:
                # Keep an ambiguous key blocked while at least one of its
                # conflicting domains is still covered by DIRECT policy.
                remains_direct = any(
                    self._matches_direct_domain(domain, allowed_domains)
                    for domain in transaction.domains
                )

            if not remains_direct:
                stale_keys.append(transaction_key)

        for transaction_key in stale_keys:
            self._pending.pop(transaction_key, None)

        return len(stale_keys)

    def parse_lines(
        self,
        lines: tuple[str, ...] | list[str] | str,
        direct_domains: tuple[str, ...],
    ) -> tuple[SmartRoutingDnsResponse, ...]:
        allowed_domains = {
            self._normalize_domain(domain)
            for domain in direct_domains
            if self._normalize_domain(domain)
        }

        # Also expire stale state when parse_lines is used independently
        # of the coordinator.
        self.prune_pending(tuple(allowed_domains))

        if not allowed_domains:
            return ()

        if isinstance(lines, str):
            raw_lines = lines.splitlines()
        else:
            raw_lines = list(lines)

        responses: list[SmartRoutingDnsResponse] = []

        for raw_line in raw_lines:
            line = raw_line.strip()
            if not line:
                continue

            prefix_match = re.search(
                r"dnsmasq\[(?P<process_id>\d+)\]:\s*",
                line,
            )
            if prefix_match is None:
                continue

            process_id = prefix_match.group("process_id")
            payload = line[prefix_match.end() :].strip()
            normalized_line = f"{process_id}:{payload}"

            query = self._QUERY.match(normalized_line)
            if query:
                domain = self._normalize_domain(query.group("domain"))
                transaction_key = (
                    query.group("process_id"),
                    query.group("transaction_id"),
                )

                observed_at = monotonic()
                if transaction_key in self._pending:
                    existing = self._pending[transaction_key]
                    if isinstance(existing, _PendingTransaction):
                        if existing.domain != domain:
                            # Never attribute a reply to one of two conflicting domains.
                            self._pending[transaction_key] = _AmbiguousTransaction(
                                domains={existing.domain, domain},
                                last_activity=observed_at,
                            )
                        else:
                            # Repeated queries for the same domain preserve
                            # collected A/AAAA records.
                            existing.last_activity = observed_at
                    else:
                        existing.domains.add(domain)
                        existing.last_activity = observed_at
                elif self._matches_direct_domain(domain, allowed_domains):
                    self._pending[transaction_key] = _PendingTransaction(
                        process_id=int(query.group("process_id")),
                        transaction_id=query.group("transaction_id"),
                        domain=domain,
                        ipv4_addresses=set(),
                        ipv6_addresses=set(),
                        last_activity=observed_at,
                    )
                    while len(self._pending) > self.MAX_PENDING:
                        oldest_key = next(iter(self._pending))
                        self._pending.pop(oldest_key)

                continue

            reply = self._REPLY.match(normalized_line)
            if not reply:
                continue

            transaction_key = (
                reply.group("process_id"),
                reply.group("transaction_id"),
            )
            transaction = self._pending.get(transaction_key)

            if transaction is None:
                continue

            transaction.last_activity = monotonic()
            if isinstance(transaction, _AmbiguousTransaction):
                continue

            value = reply.group("value")

            try:
                address = IPv4Address(value)
            except ValueError:
                try:
                    address = IPv6Address(value)
                except ValueError:
                    # CNAME and other non-address replies are intentionally ignored.
                    continue

            if isinstance(address, IPv4Address):
                transaction.ipv4_addresses.add(str(address))
            else:
                transaction.ipv6_addresses.add(str(address))

            responses.append(
                SmartRoutingDnsResponse(
                    process_id=transaction.process_id,
                    transaction_id=transaction.transaction_id,
                    domain=transaction.domain,
                    ipv4_addresses=tuple(sorted(transaction.ipv4_addresses)),
                    ipv6_addresses=tuple(sorted(transaction.ipv6_addresses)),
                )
            )

            # A DNS response may contain several A records. Keep the
            # transaction alive so subsequent A replies accumulate into it.
            #
            # The state is consumed by the coordinator on every polling
            # iteration; replacing the stored set with the latest response
            # is enough to carry the transaction across chunk boundaries.
            self._pending[transaction_key] = transaction

        return self._deduplicate_responses(responses)

    @classmethod
    def _parse_responses(
        cls,
        output: str,
        allowed_domains: set[str],
    ) -> tuple[SmartRoutingDnsResponse, ...]:
        """
        Stateless parser retained for existing callers/tests.

        This parses a complete log block in one pass. Incremental callers
        should use parse_lines(), which preserves transactions across polls.
        """
        transactions: dict[
            tuple[str, str],
            tuple[str, set[str], set[str]] | None,
        ] = {}

        for raw_line in (output or "").splitlines():
            line = raw_line.strip()

            prefix_match = re.search(
                r"dnsmasq\[(?P<process_id>\d+)\]:\s*",
                line,
            )
            if prefix_match is None:
                continue

            process_id = prefix_match.group("process_id")
            payload = line[prefix_match.end() :].strip()
            line = f"{process_id}:{payload}"

            query = cls._QUERY.match(line)
            if query:
                domain = cls._normalize_domain(query.group("domain"))
                transaction_key = (
                    query.group("process_id"),
                    query.group("transaction_id"),
                )

                if transaction_key in transactions:
                    existing = transactions[transaction_key]
                    if existing is not None and existing[0] != domain:
                        transactions[transaction_key] = None
                elif cls._matches_direct_domain(domain, allowed_domains):
                    transactions[transaction_key] = (domain, set(), set())

                continue

            reply = cls._REPLY.match(line)
            if not reply:
                continue

            transaction = transactions.get(
                (
                    reply.group("process_id"),
                    reply.group("transaction_id"),
                )
            )

            if transaction is None:
                continue

            try:
                address = IPv4Address(reply.group("value"))
            except ValueError:
                try:
                    address = IPv6Address(reply.group("value"))
                except ValueError:
                    continue

            domain, ipv4_addresses, ipv6_addresses = transaction
            if isinstance(address, IPv4Address):
                ipv4_addresses.add(str(address))
            else:
                ipv6_addresses.add(str(address))

        responses: list[SmartRoutingDnsResponse] = []
        for (process_id, transaction_id), transaction in transactions.items():
            if transaction is None:
                continue
            domain, ipv4_addresses, ipv6_addresses = transaction
            if not ipv4_addresses and not ipv6_addresses:
                continue
            responses.append(
                SmartRoutingDnsResponse(
                    process_id=int(process_id),
                    transaction_id=transaction_id,
                    domain=domain,
                    ipv4_addresses=tuple(sorted(ipv4_addresses)),
                    ipv6_addresses=tuple(sorted(ipv6_addresses)),
                ),
            )

        return tuple(
            sorted(
                responses,
                key=lambda item: (
                    item.process_id,
                    item.transaction_id,
                    item.domain,
                ),
            )
        )

    @staticmethod
    def _deduplicate_responses(
        responses: list[SmartRoutingDnsResponse],
    ) -> tuple[SmartRoutingDnsResponse, ...]:
        latest: dict[tuple[int, str, str], SmartRoutingDnsResponse] = {}

        for response in responses:
            key = (
                response.process_id,
                response.transaction_id,
                response.domain,
            )
            # Moving a repeated transaction to the end preserves the order of
            # its final reply in the DNS log. This matters when bootstrapping
            # per-domain state from a historical log containing many queries.
            latest.pop(key, None)
            latest[key] = response

        return tuple(latest.values())

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        return domain.strip().lower().rstrip(".")

    @staticmethod
    def _matches_direct_domain(
        domain: str,
        allowed_domains: set[str],
    ) -> bool:
        return any(
            domain == allowed or domain.endswith(f".{allowed}")
            for allowed in allowed_domains
        )
