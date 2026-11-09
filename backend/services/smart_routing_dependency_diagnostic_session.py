from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from ipaddress import ip_address

from backend.services.smart_routing_dependency_diagnostic import (
    SmartRoutingDependencyDnsParser,
)
from backend.services.smart_routing_dependency_diagnostic_service import (
    DependencyDiagnosticGroup,
    SmartRoutingDependencyDiagnosticService,
)
from backend.services.smart_routing_dns_log_reader import (
    SmartRoutingDnsLogCursor,
    SmartRoutingDnsLogReader,
)

_QUERY_SOURCE_RE = re.compile(
    r"query\[(?:A|AAAA|HTTPS|CNAME|PTR|SRV|TXT|MX)\]\s+\S+\s+from\s+(?P<source>\S+)"
)


@dataclass
class DependencyDiagnosticSession:
    token: str
    site_domain: str
    client_ip: str
    started_at: float
    expires_at: float
    cursor: SmartRoutingDnsLogCursor
    parser: SmartRoutingDependencyDnsParser
    last_group: DependencyDiagnosticGroup | None = None
    last_poll_completed_at: float | None = None
    retained_until: float | None = None


class SmartRoutingDependencyDiagnosticSessionService:
    """
    Runtime coordinator for dependency diagnostics.

    Sessions are intentionally in-memory. The DNS log cursor and parser state
    belong to an active diagnostic session and must survive polling requests.
    """

    MIN_DURATION = 20
    MAX_DURATION = 60
    DEFAULT_DURATION = 30
    # Keep completed results available long enough to review and commit rules.
    RESULT_RETENTION_SECONDS = 30 * 60

    def __init__(
        self,
        reader: SmartRoutingDnsLogReader,
        analyzer: SmartRoutingDependencyDiagnosticService,
    ) -> None:
        self._reader = reader
        self._analyzer = analyzer
        self._sessions: dict[str, DependencyDiagnosticSession] = {}

    def start(
        self,
        site_domain: str,
        client_ip: str,
        duration_seconds: int | None = None,
    ) -> dict[str, object]:
        domain = self._normalize_domain(site_domain)
        client = self._normalize_client_ip(client_ip)

        duration = int(
            duration_seconds if duration_seconds is not None else self.DEFAULT_DURATION
        )

        if not self.MIN_DURATION <= duration <= self.MAX_DURATION:
            raise ValueError(
                f"duration_seconds must be between "
                f"{self.MIN_DURATION} and {self.MAX_DURATION}",
            )

        self._cleanup_expired()

        now = time.time()
        token = uuid.uuid4().hex

        session = DependencyDiagnosticSession(
            token=token,
            site_domain=domain,
            client_ip=client,
            started_at=now,
            expires_at=now + duration,
            cursor=self._reader.current_cursor(),
            parser=SmartRoutingDependencyDnsParser(),
        )

        self._sessions[token] = session

        return self._session_payload(session)

    def poll(
        self,
        token: str,
        *,
        direct_ips: set[str],
        direct_rules: tuple[str, ...],
    ) -> tuple[dict[str, object], DependencyDiagnosticGroup]:
        session = self._sessions.get(token)

        if session is None:
            raise KeyError("diagnostic session not found")

        read_result = self._reader.read(session.cursor)
        session.cursor = read_result.cursor

        if read_result.reset:
            session.parser.reset()

        filtered_lines = self._filter_client_lines(
            read_result.lines,
            session.client_ip,
        )

        session.parser.feed(
            "\n".join(filtered_lines),
        )

        raw_resources = session.parser.resources(
            client_ip=session.client_ip,
        )

        group = self._analyzer.analyze(
            session.site_domain,
            raw_resources,
            direct_ips=direct_ips,
            direct_rules=direct_rules,
        )

        # Decide completion after draining the log so the final poll cannot
        # be marked running merely because the read crossed the end boundary.
        now = time.time()
        running = now < session.expires_at

        session.last_group = group
        session.last_poll_completed_at = now

        payload = self._session_payload(
            session,
            running=running,
            group=group,
        )

        if not running:
            # Keep the last analyzed group briefly so the user can select
            # candidates after the observation window has closed.
            session.retained_until = now + self.RESULT_RETENTION_SECONDS

        return payload, group

    def get_group(self, token: str) -> DependencyDiagnosticGroup:
        session = self._sessions.get(token)

        if session is None or session.last_group is None:
            raise KeyError("diagnostic session result not found")

        if time.time() < session.expires_at:
            raise ValueError(
                "diagnostic session is still running; wait for it to finish"
            )
        if (
            session.last_poll_completed_at is None
            or session.last_poll_completed_at < session.expires_at
        ):
            raise ValueError(
                "final diagnostic results were not collected; "
                "poll the session after it finishes"
            )

        if session.retained_until is not None and time.time() >= session.retained_until:
            self._sessions.pop(token, None)
            raise KeyError("diagnostic session result not found")

        return session.last_group

    def stop(self, token: str) -> None:
        self._sessions.pop(token, None)

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [
            token
            for token, session in self._sessions.items()
            if (session.retained_until is not None and session.retained_until <= now)
            or (session.retained_until is None and session.expires_at <= now)
        ]

        for token in expired:
            self._sessions.pop(token, None)

    @staticmethod
    def _filter_client_lines(
        lines: tuple[str, ...],
        client_ip: str,
    ) -> tuple[str, ...]:
        """
        Keep only queries originating from the diagnostic client plus all
        replies. dnsmasq reply records do not contain the client address.
        """
        result: list[str] = []

        for line in lines:
            match = _QUERY_SOURCE_RE.search(line)

            if match is not None:
                if match.group("source") != client_ip:
                    continue

            result.append(line)

        return tuple(result)

    @staticmethod
    def _normalize_domain(value: str) -> str:
        value = str(value).strip().lower().rstrip(".")

        if value.startswith("*."):
            value = value[2:]

        if not value or "." not in value:
            raise ValueError(
                "site_domain must contain at least two labels",
            )

        if any(
            not (
                part
                and len(part) <= 63
                and part[0].isalnum()
                and part[-1].isalnum()
                and all(char.isalnum() or char == "-" for char in part)
            )
            for part in value.split(".")
        ):
            raise ValueError("invalid site_domain")

        return value

    @staticmethod
    def _normalize_client_ip(value: str) -> str:
        try:
            parsed = ip_address(str(value).strip())
        except ValueError as exc:
            raise ValueError("invalid client_ip") from exc

        if parsed.version != 4:
            raise ValueError("client_ip must be IPv4")

        return str(parsed)

    @staticmethod
    def _session_payload(
        session: DependencyDiagnosticSession,
        *,
        running: bool | None = None,
        group: DependencyDiagnosticGroup | None = None,
    ) -> dict[str, object]:
        is_running = (
            running if running is not None else time.time() < session.expires_at
        )

        payload: dict[str, object] = {
            "token": session.token,
            "site_domain": session.site_domain,
            "client_ip": session.client_ip,
            "started_at": int(session.started_at),
            "expires_at": int(session.expires_at),
            "running": is_running,
            "remaining_seconds": max(
                0,
                int(session.expires_at - time.time()),
            ),
        }

        if group is not None:
            payload["summary"] = {
                "observed": group.summary.observed,
                "direct": group.summary.direct,
                "vpn": group.summary.vpn,
                "partial": group.summary.partial,
                "unknown": group.summary.unknown,
                "uncovered": group.summary.uncovered,
            }

            payload["resources"] = [
                {
                    "hostname": item.hostname,
                    "ips": list(item.ips),
                    "cname_chain": list(item.cname_chain),
                    "query_count": item.query_count,
                    "relation": item.relation,
                    "routing": item.routing,
                    "covered_by_rule": item.covered_by_rule,
                    "rule_domain": item.rule_domain,
                    "candidate_for_direct": item.candidate_for_direct,
                    "selection_allowed": item.selection_allowed,
                    "category": item.category,
                    "category_detail": item.category_detail,
                    "brand_alias": item.brand_alias,
                    "synthetic": item.synthetic,
                    "observed_hostnames": list(item.observed_hostnames),
                    "relevance": item.relevance,
                    "relevance_score": item.relevance_score,
                    "dependency_reasons": list(item.dependency_reasons),
                    "related_hostnames": list(item.related_hostnames),
                    "recommended_for_direct": item.recommended_for_direct,
                }
                for item in group.resources
            ]

        return payload
