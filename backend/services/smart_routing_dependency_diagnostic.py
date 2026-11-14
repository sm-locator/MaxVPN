from __future__ import annotations

import ipaddress
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field

_QTYPE_PATTERN = r"A|AAAA|HTTPS|CNAME|PTR|SRV|TXT|MX"
_QUERY_RE = re.compile(
    rf"query\[(?P<qtype>{_QTYPE_PATTERN})\]\s+"
    r"(?P<hostname>\S+)\s+from\s+(?P<source>\S+)"
)
_TRANSACTION_QUERY_RE = re.compile(
    rf"dnsmasq\[(?P<pid>\d+)\]:\s+(?P<query_id>\d+)\s+"
    rf"(?P<peer>\S+)\s+query\[(?P<qtype>{_QTYPE_PATTERN})\]\s+"
    r"(?P<hostname>\S+)\s+from\s+(?P<source>\S+)"
)
_REPLY_RE = re.compile(r"(?:reply|cached)\s+(?P<hostname>\S+)\s+is\s+(?P<answer>\S+)")
_TRANSACTION_REPLY_RE = re.compile(
    r"dnsmasq\[(?P<pid>\d+)\]:\s+(?P<query_id>\d+)\s+"
    r"(?P<peer>\S+)\s+(?:reply|cached)\s+(?P<hostname>\S+)\s+"
    r"is\s+(?P<answer>\S+)"
)
_SYSLOG_TIME_RE = re.compile(
    r"^(?P<month>[A-Z][a-z]{2})\s+\d{1,2}\s+"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
)
_DNSMASQ_TIME_RE = re.compile(
    r"dnsmasq\[\d+\]:\s+(?P<hour>\d{2}):" r"(?P<minute>\d{2}):(?P<second>\d{2})"
)


@dataclass(frozen=True)
class PendingQuery:
    hostname: str
    qtype: str
    source: str
    query_time: int | None = None
    transaction_key: tuple[str, str, str] | None = None


@dataclass
class DependencyRecord:
    hostname: str
    query_count: int = 0
    query_count_by_source: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    sources: set[str] = field(default_factory=set)
    ips_by_source: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    cname_targets_by_source: dict[str, set[str]] = field(
        default_factory=lambda: defaultdict(set)
    )
    query_times_by_source: dict[str, set[int]] = field(
        default_factory=lambda: defaultdict(set)
    )
    first_seen: int = 0
    last_seen: int = 0


@dataclass(frozen=True)
class DependencyDiagnosticResource:
    hostname: str
    ips: tuple[str, ...]
    cname_chain: tuple[str, ...]
    query_count: int
    first_seen: int = 0
    last_seen: int = 0
    query_times: tuple[int, ...] = ()


class SmartRoutingDependencyDnsParser:
    """Incremental dnsmasq parser with client-safe A/reply correlation.

    Query IDs from the appliance event log are used when available. Older
    dnsmasq log lines remain supported through per-hostname/qtype pending queues.
    Query timestamps are seconds since midnight and are used only as a heuristic
    for classifying nearby DNS activity; they do not prove HTTP dependencies.
    """

    MAX_PENDING = 4096

    def __init__(self) -> None:
        self.pending: dict[tuple[str, str], deque[PendingQuery]] = defaultdict(deque)
        self.transactions: dict[tuple[str, str, str], PendingQuery] = {}
        self.records: dict[str, DependencyRecord] = {}
        self._event_index = 0

    def feed(self, data: str) -> None:
        for raw_line in (data or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue

            tx_query = _TRANSACTION_QUERY_RE.search(line)
            query = tx_query or _QUERY_RE.search(line)
            if query:
                hostname = self._normalize_hostname(query.group("hostname"))
                qtype = query.group("qtype").upper()
                source = query.group("source").strip()
                if not hostname or not source:
                    continue

                self._event_index += 1
                query_time = self._time_of_day(line)
                transaction_key = None
                if tx_query:
                    transaction_key = (
                        tx_query.group("pid"),
                        tx_query.group("query_id"),
                        tx_query.group("peer"),
                    )

                pending = PendingQuery(
                    hostname=hostname,
                    qtype=qtype,
                    source=source,
                    query_time=query_time,
                    transaction_key=transaction_key,
                )
                if transaction_key is not None:
                    self.transactions[transaction_key] = pending
                    while len(self.transactions) > self.MAX_PENDING:
                        self.transactions.pop(next(iter(self.transactions)))
                else:
                    queue = self.pending[(hostname, qtype)]
                    queue.append(pending)
                    while len(queue) > self.MAX_PENDING:
                        queue.popleft()

                record = self.records.setdefault(
                    hostname,
                    DependencyRecord(hostname=hostname),
                )
                record.query_count += 1
                record.query_count_by_source[source] += 1
                record.sources.add(source)
                if query_time is not None:
                    record.query_times_by_source[source].add(query_time)
                if record.first_seen == 0:
                    record.first_seen = self._event_index
                record.last_seen = self._event_index
                continue

            tx_reply = _TRANSACTION_REPLY_RE.search(line)
            reply = tx_reply or _REPLY_RE.search(line)
            if not reply:
                continue

            hostname = self._normalize_hostname(reply.group("hostname"))
            answer = str(reply.group("answer") or "").strip()
            if not hostname or not answer:
                continue

            pending = None
            if tx_reply:
                transaction_key = (
                    tx_reply.group("pid"),
                    tx_reply.group("query_id"),
                    tx_reply.group("peer"),
                )
                # dnsmasq can log a CNAME hop and then the terminal IPv4 answer
                # under the same query transaction. Keep the original pending
                # query across intermediate CNAME replies; consume it only when
                # the transaction reaches a terminal answer/status.
                pending = self.transactions.get(transaction_key)
                if pending is not None:
                    is_intermediate_cname = pending.qtype in {
                        "A",
                        "AAAA",
                        "HTTPS",
                        "CNAME",
                    } and (answer == "<CNAME>" or self._valid_hostname(answer))
                    if not is_intermediate_cname:
                        self.transactions.pop(transaction_key, None)
            else:
                # Replies without transaction IDs do not expose the original
                # qtype. Use the answer itself to avoid letting an HTTPS NODATA
                # reply consume a pending A query for the same hostname.
                try:
                    parsed_answer = ipaddress.ip_address(answer)
                except ValueError:
                    parsed_answer = None

                if isinstance(parsed_answer, ipaddress.IPv4Address):
                    pending = self._consume_pending(hostname, "A")
                elif isinstance(parsed_answer, ipaddress.IPv6Address):
                    pending = self._consume_pending(hostname, "AAAA")
                elif answer == "<CNAME>" or self._valid_hostname(answer):
                    pending = self._consume_pending(hostname, "A")
                    if pending is None:
                        pending = self._consume_pending(hostname, "CNAME")
                else:
                    # NODATA/NXDOMAIN/SERVFAIL cannot safely identify a qtype.
                    pending = None

            if pending is None:
                continue

            self._event_index += 1
            try:
                parsed_ip = ipaddress.ip_address(answer)
            except ValueError:
                parsed_ip = None

            # A terminal IPv4 reply belongs to the original A query, even when
            # dnsmasq names the final CNAME target on the reply line.
            if pending.qtype == "A" and isinstance(parsed_ip, ipaddress.IPv4Address):
                record = self.records.setdefault(
                    pending.hostname,
                    DependencyRecord(hostname=pending.hostname),
                )
                record.ips_by_source[pending.source].add(str(parsed_ip))
            elif pending.qtype in {"A", "CNAME"} and self._valid_hostname(answer):
                target = self._normalize_hostname(answer)
                # Attach each CNAME hop to the hostname named by this reply,
                # not always to the initial query name. This preserves multi-hop
                # chains while keeping the source association from the client query.
                if target and target != hostname:
                    record = self.records.setdefault(
                        hostname,
                        DependencyRecord(hostname=hostname),
                    )
                    record.cname_targets_by_source[pending.source].add(target)
                else:
                    record = self.records.setdefault(
                        pending.hostname,
                        DependencyRecord(hostname=pending.hostname),
                    )
            else:
                record = self.records.setdefault(
                    pending.hostname,
                    DependencyRecord(hostname=pending.hostname),
                )

            if record.first_seen == 0:
                record.first_seen = self._event_index
            record.last_seen = self._event_index

    def resources(
        self,
        *,
        client_ip: str | None = None,
    ) -> tuple[DependencyDiagnosticResource, ...]:
        result: list[DependencyDiagnosticResource] = []

        for record in self.records.values():
            matching_sources = {client_ip} if client_ip else set(record.sources)
            matching_sources.intersection_update(record.sources)
            if not matching_sources:
                continue

            ips: set[str] = set()
            query_times: set[int] = set()
            for source in matching_sources:
                ips.update(record.ips_by_source.get(source, set()))
                query_times.update(record.query_times_by_source.get(source, set()))

            cname_chain = self._build_cname_chain(
                record.hostname,
                matching_sources,
            )
            # CNAME aliases resolve to the terminal address of their chain.
            # On some dnsmasq logs the target's A lookup is attributed to the
            # local resolver rather than the original LAN client, so use the
            # explicitly observed CNAME chain as the relation and fall back to
            # the target record's known addresses when no client-keyed address
            # is present. This is address evidence, not proof of HTTP dependency.
            for chained_hostname in cname_chain[1:]:
                chained_record = self.records.get(chained_hostname)
                if chained_record is None:
                    continue
                chained_ips: set[str] = set()
                for source in matching_sources:
                    chained_ips.update(chained_record.ips_by_source.get(source, set()))
                if not chained_ips:
                    for source_ips in chained_record.ips_by_source.values():
                        chained_ips.update(source_ips)
                ips.update(chained_ips)
            query_count = sum(
                record.query_count_by_source.get(source, 0)
                for source in matching_sources
            )

            result.append(
                DependencyDiagnosticResource(
                    hostname=record.hostname,
                    ips=tuple(sorted(ips)),
                    cname_chain=cname_chain,
                    query_count=query_count,
                    first_seen=record.first_seen,
                    last_seen=record.last_seen,
                    query_times=tuple(sorted(query_times)),
                )
            )

        return tuple(sorted(result, key=lambda item: item.hostname))

    def reset(self) -> None:
        self.pending.clear()
        self.transactions.clear()
        self.records.clear()
        self._event_index = 0

    def _consume_pending(self, hostname: str, qtype: str) -> PendingQuery | None:
        queue = self.pending.get((hostname, qtype))
        if not queue:
            return None
        pending = queue.popleft()
        if not queue:
            self.pending.pop((hostname, qtype), None)
        return pending

    def _build_cname_chain(
        self,
        hostname: str,
        sources: set[str],
    ) -> tuple[str, ...]:
        result: list[str] = []
        current = hostname
        visited: set[str] = set()

        while current and current not in visited:
            visited.add(current)
            result.append(current)
            record = self.records.get(current)
            if record is None:
                break

            targets: set[str] = set()
            for source in sources:
                targets.update(record.cname_targets_by_source.get(source, set()))
            # Intermediate CNAME target lookups may be logged under dnsmasq's
            # resolver source, rather than the originating LAN client. Only use
            # this fallback when the client-specific hop is absent.
            if not targets:
                for source_targets in record.cname_targets_by_source.values():
                    targets.update(source_targets)
            if not targets:
                break
            current = sorted(targets)[0]

        return tuple(result)

    @staticmethod
    def _time_of_day(line: str) -> int | None:
        match = _SYSLOG_TIME_RE.match(line) or _DNSMASQ_TIME_RE.search(line)
        if match is None:
            return None
        return (
            int(match.group("hour")) * 3600
            + int(match.group("minute")) * 60
            + int(match.group("second"))
        )

    @classmethod
    def _normalize_hostname(cls, hostname: str) -> str:
        hostname = str(hostname or "").strip().lower().rstrip(".")
        if not cls._valid_hostname(hostname):
            return ""
        return hostname

    @staticmethod
    def _valid_hostname(hostname: str) -> bool:
        value = str(hostname or "").strip().lower().rstrip(".")
        if not value or len(value) > 253 or "." not in value:
            return False
        return all(
            label
            and len(label) <= 63
            and label[0].isalnum()
            and label[-1].isalnum()
            and all(ch.isalnum() or ch == "-" for ch in label)
            for label in value.split(".")
        )
