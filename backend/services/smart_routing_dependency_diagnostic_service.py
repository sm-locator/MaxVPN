from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Address, ip_address
from typing import Iterable

from backend.services.smart_routing_dependency_diagnostic import (
    DependencyDiagnosticResource,
)


@dataclass(frozen=True, slots=True)
class DependencyResourceAnalysis:
    hostname: str
    ips: tuple[str, ...]
    cname_chain: tuple[str, ...]
    query_count: int
    relation: str
    routing: str
    covered_by_rule: bool
    rule_domain: str | None
    candidate_for_direct: bool
    synthetic: bool = False
    observed_hostnames: tuple[str, ...] = ()
    first_seen: int = 0
    last_seen: int = 0
    relevance: str = "background"
    relevance_score: int = 0
    dependency_reasons: tuple[str, ...] = ()
    related_hostnames: tuple[str, ...] = ()
    recommended_for_direct: bool = False
    category: str = "background"
    category_detail: str = "Фоновый DNS-запрос"
    brand_alias: bool = False
    selection_allowed: bool = False
    query_times: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class DependencyDiagnosticSummary:
    observed: int
    direct: int
    vpn: int
    partial: int
    unknown: int
    uncovered: int


@dataclass(frozen=True, slots=True)
class DependencyDiagnosticGroup:
    site_domain: str
    resources: tuple[DependencyResourceAnalysis, ...]
    summary: DependencyDiagnosticSummary


class SmartRoutingDependencyDiagnosticService:
    """Classify observed DNS resources and identify safe DIRECT candidates.

    Dependency relevance is heuristic: DNS observations can show that hosts
    are requested together, share addresses, or are linked by CNAME, but they
    cannot prove that a particular host is required by the rendered page.

    Repeated observed subdomains can be grouped into a synthetic suffix for
    display, but synthetic resources are never eligible for DIRECT selection.
    The service is read-only and never applies routing rules.
    """

    # MAXVPN-DIAGNOSTIC-PARITY-V1
    RELATION_WINDOW_SECONDS = 5
    KNOWN_BRAND_ALIASES: dict[str, tuple[str, ...]] = {
        "2gis.ru": ("2gis.com",),
    }
    WINDOWS_CONNECTIVITY_SUFFIXES = (
        "msftconnecttest.com",
        "msftncsi.com",
    )
    REVERSE_DNS_SUFFIXES = ("in-addr.arpa", "ip6.arpa")

    def analyze(
        self,
        site_domain: str,
        resources: Iterable[DependencyDiagnosticResource],
        *,
        direct_ips: Iterable[str] = (),
        direct_rules: Iterable[str] = (),
    ) -> DependencyDiagnosticGroup:
        site_domain = self._normalize_domain(site_domain)

        direct_ip_set = {
            str(value).strip() for value in direct_ips if str(value).strip()
        }

        rules = tuple(
            self._normalize_domain(value)
            for value in direct_rules
            if str(value).strip()
        )

        observed_resources = tuple(resources)
        target_times = tuple(
            sorted(
                {
                    timestamp
                    for resource in observed_resources
                    if self._is_target_site(
                        self._normalize_domain(resource.hostname), site_domain
                    )
                    for timestamp in getattr(resource, "query_times", ())
                }
            )
        )

        analyzed: list[DependencyResourceAnalysis] = []
        for resource in observed_resources:
            analyzed.append(
                self._analyze_resource(
                    resource,
                    site_domain=site_domain,
                    target_times=target_times,
                    direct_ip_set=direct_ip_set,
                    rules=rules,
                )
            )

        raw_hostnames = tuple(sorted({item.hostname for item in analyzed}))

        aggregates = self._build_dependency_aggregates(
            analyzed,
            raw_hostnames=raw_hostnames,
            site_domain=site_domain,
            target_times=target_times,
            direct_ip_set=direct_ip_set,
            rules=rules,
        )

        all_resources = analyzed + aggregates
        all_resources = self._add_relevance(
            all_resources,
            site_domain=site_domain,
        )

        all_resources.sort(
            key=lambda item: (
                item.relevance == "background",
                not item.recommended_for_direct,
                item.relevance_score * -1,
                item.relation != "same_site",
                not item.synthetic,
                item.hostname,
            )
        )

        return DependencyDiagnosticGroup(
            site_domain=site_domain,
            resources=tuple(all_resources),
            summary=self._summary(analyzed),
        )

    def _analyze_resource(
        self,
        resource: DependencyDiagnosticResource,
        *,
        site_domain: str,
        target_times: tuple[int, ...],
        direct_ip_set: set[str],
        rules: tuple[str, ...],
    ) -> DependencyResourceAnalysis:
        hostname = self._normalize_domain(resource.hostname)
        relation = self._relation(hostname, site_domain)
        category, category_detail, brand_alias = self._classify_resource(
            hostname,
            site_domain=site_domain,
            query_times=tuple(getattr(resource, "query_times", ()) or ()),
            target_times=target_times,
        )
        covered_rule = self._matching_rule(hostname, rules)
        # DIRECT eligibility deliberately considers IPv4 A answers only.
        ips = self._normalize_ipv4_addresses(resource.ips)
        routing = self._routing(ips, direct_ip_set, covered_rule is not None)
        selection_allowed = bool(
            not category == "background"
            and (relation == "same_site" or brand_alias)
            and ips
            and routing == "vpn"
            and covered_rule is None
            and not bool(getattr(resource, "synthetic", False))
        )

        return DependencyResourceAnalysis(
            hostname=hostname,
            ips=ips,
            cname_chain=tuple(resource.cname_chain),
            query_count=resource.query_count,
            relation=relation,
            routing=routing,
            covered_by_rule=covered_rule is not None,
            rule_domain=covered_rule,
            candidate_for_direct=selection_allowed,
            synthetic=False,
            observed_hostnames=(hostname,),
            first_seen=resource.first_seen,
            last_seen=resource.last_seen,
            category=category,
            category_detail=category_detail,
            brand_alias=brand_alias,
            selection_allowed=selection_allowed,
            query_times=tuple(sorted(set(getattr(resource, "query_times", ()) or ()))),
        )

    def _build_dependency_aggregates(
        self,
        resources: list[DependencyResourceAnalysis],
        *,
        raw_hostnames: tuple[str, ...],
        site_domain: str,
        target_times: tuple[int, ...],
        direct_ip_set: set[str],
        rules: tuple[str, ...],
    ) -> list[DependencyResourceAnalysis]:
        candidates = self._dependency_suffixes(raw_hostnames)

        aggregates: list[DependencyResourceAnalysis] = []

        for suffix in candidates:
            if suffix in raw_hostnames:
                continue

            children = [
                resource
                for resource in resources
                if (
                    resource.hostname.endswith("." + suffix)
                    and len(resource.hostname.split(".")) == len(suffix.split(".")) + 1
                )
            ]

            if len(children) < 2:
                continue

            ips = tuple(sorted({ip for child in children for ip in child.ips}))

            cname_chain = tuple(
                dict.fromkeys(
                    cname for child in children for cname in child.cname_chain
                )
            )

            query_count = sum(child.query_count for child in children)
            first_seen = min(
                (child.first_seen for child in children if child.first_seen),
                default=0,
            )
            last_seen = max(
                (child.last_seen for child in children if child.last_seen),
                default=0,
            )

            covered_rule = self._matching_rule(suffix, rules)
            routing = self._routing(ips, direct_ip_set, covered_rule is not None)
            query_times = tuple(
                sorted(
                    {timestamp for child in children for timestamp in child.query_times}
                )
            )
            category, category_detail, brand_alias = self._classify_resource(
                suffix,
                site_domain=site_domain,
                query_times=query_times,
                target_times=target_times,
            )

            # Aggregated suffixes are inferred, not observed DNS query names.
            # Keep them visible for insight, but never allow adding them to DIRECT.
            aggregates.append(
                DependencyResourceAnalysis(
                    hostname=suffix,
                    ips=ips,
                    cname_chain=cname_chain,
                    query_count=query_count,
                    relation=self._relation(suffix, site_domain),
                    routing=routing,
                    covered_by_rule=covered_rule is not None,
                    rule_domain=covered_rule,
                    candidate_for_direct=False,
                    synthetic=True,
                    observed_hostnames=tuple(
                        sorted(child.hostname for child in children)
                    ),
                    first_seen=first_seen,
                    last_seen=last_seen,
                    category=category,
                    category_detail=category_detail,
                    brand_alias=brand_alias,
                    selection_allowed=False,
                    query_times=query_times,
                )
            )

        return aggregates

    @classmethod
    def _dependency_suffixes(
        cls,
        hostnames: tuple[str, ...],
    ) -> tuple[str, ...]:
        suffix_children: dict[str, set[str]] = {}

        for hostname in hostnames:
            labels = hostname.split(".")

            if len(labels) < 3:
                continue

            suffix = ".".join(labels[1:])
            suffix_children.setdefault(suffix, set()).add(hostname)

        viable = {
            suffix for suffix, children in suffix_children.items() if len(children) >= 2
        }

        specific = {
            suffix
            for suffix in viable
            if not any(
                suffix != other and other.endswith("." + suffix) for other in viable
            )
        }

        return tuple(sorted(specific))

    def _add_relevance(
        self,
        resources: list[DependencyResourceAnalysis],
        *,
        site_domain: str,
    ) -> list[DependencyResourceAnalysis]:
        anchors = tuple(
            item
            for item in resources
            if item.relation == "same_site" and not item.synthetic
        )

        enriched: list[DependencyResourceAnalysis] = []

        for item in resources:
            score, reasons, related = self._relevance_for(
                item,
                site_domain=site_domain,
                anchors=anchors,
            )
            relevance = self._relevance_label(score)
            enriched.append(
                DependencyResourceAnalysis(
                    hostname=item.hostname,
                    ips=item.ips,
                    cname_chain=item.cname_chain,
                    query_count=item.query_count,
                    relation=item.relation,
                    routing=item.routing,
                    covered_by_rule=item.covered_by_rule,
                    rule_domain=item.rule_domain,
                    candidate_for_direct=item.candidate_for_direct,
                    synthetic=item.synthetic,
                    observed_hostnames=item.observed_hostnames,
                    first_seen=item.first_seen,
                    last_seen=item.last_seen,
                    relevance=relevance,
                    relevance_score=score,
                    dependency_reasons=tuple(reasons),
                    related_hostnames=tuple(related),
                    recommended_for_direct=item.selection_allowed,
                    category=item.category,
                    category_detail=item.category_detail,
                    brand_alias=item.brand_alias,
                    selection_allowed=item.selection_allowed,
                    query_times=item.query_times,
                )
            )

        return enriched

    def _relevance_for(
        self,
        item: DependencyResourceAnalysis,
        *,
        site_domain: str,
        anchors: tuple[DependencyResourceAnalysis, ...],
    ) -> tuple[int, list[str], list[str]]:
        reasons: list[str] = []
        related: set[str] = set()

        if item.hostname == site_domain:
            score = 100
            reasons.append("основной домен")
        elif item.relation == "same_site":
            score = 75
            reasons.append("поддомен основного домена")
        else:
            score = 10
            reasons.append("внешний ресурс")

        if item.synthetic:
            score = 0
            child_scores = []
            for hostname in item.observed_hostnames:
                child = next(
                    (anchor for anchor in anchors if anchor.hostname == hostname), None
                )
                if child is not None:
                    child_scores.append(child.relevance_score)
            if not child_scores:
                child_scores = [10]
            score = max(child_scores) + (10 if len(item.observed_hostnames) >= 2 else 0)
            reasons.append("повторяющиеся поддомены")

        item_ips = set(item.ips)

        for anchor in anchors:
            if anchor.hostname == item.hostname:
                continue

            shared_ip = bool(item_ips and item_ips.intersection(anchor.ips))
            cname_link = self._cname_links(item, anchor)
            proximity = self._event_proximity(item, anchor)

            relation_added = False

            if shared_ip:
                score += 20
                reasons.append("общий IP с ресурсом основного домена")
                relation_added = True

            if cname_link:
                score += 35
                reasons.append("CNAME-связь с ресурсом основного домена")
                relation_added = True

            if proximity is not None and proximity <= self.RELATION_WINDOW_SECONDS:
                score += 30
                reasons.append("DNS-запрос в пределах 5 секунд от ресурса сайта")
                relation_added = True

            if relation_added:
                related.add(anchor.hostname)

        if item.query_count >= 2:
            score += 10
            reasons.append("повторяющийся DNS-запрос")

        score = min(100, score)
        return score, self._dedupe_reasons(reasons), sorted(related)

    @staticmethod
    def _cname_links(
        item: DependencyResourceAnalysis,
        anchor: DependencyResourceAnalysis,
    ) -> bool:
        item_chain = set(item.cname_chain)
        anchor_chain = set(anchor.cname_chain)
        if item.hostname in anchor_chain or anchor.hostname in item_chain:
            return True
        if item_chain.intersection(anchor_chain):
            return True
        return bool(item_chain.intersection(anchor_chain.union({anchor.hostname})))

    @classmethod
    def _event_proximity(
        cls,
        item: DependencyResourceAnalysis,
        anchor: DependencyResourceAnalysis,
    ) -> int | None:
        if not item.query_times or not anchor.query_times:
            return None
        gaps = [
            cls._time_gap(left, right)
            for left in item.query_times
            for right in anchor.query_times
        ]
        return min(gaps) if gaps else None

    @staticmethod
    def _time_gap(left: int, right: int) -> int:
        delta = abs(int(left) - int(right)) % 86400
        return min(delta, 86400 - delta)

    @staticmethod
    def _dedupe_reasons(values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @staticmethod
    def _relevance_label(score: int) -> str:
        if score >= 80:
            return "required"
        if score >= 55:
            return "likely"
        if score >= 30:
            return "possible"
        return "background"

    @classmethod
    def _classify_resource(
        cls,
        hostname: str,
        *,
        site_domain: str,
        query_times: tuple[int, ...],
        target_times: tuple[int, ...],
    ) -> tuple[str, str, bool]:
        if cls._is_target_site(hostname, site_domain):
            return "target_site", "Ресурс целевого домена", False

        matching_alias = next(
            (
                alias
                for alias in cls.KNOWN_BRAND_ALIASES.get(site_domain, ())
                if hostname == alias or hostname.endswith("." + alias)
            ),
            None,
        )
        if matching_alias:
            return (
                "external_candidate",
                f"Домен пространства бренда ({matching_alias}); "
                "зависимость не подтверждена",
                True,
            )

        if cls._is_windows_connectivity_probe(hostname) or cls._is_reverse_dns(
            hostname
        ):
            return (
                "background",
                "Фоновый DNS-запрос — техническая проверка или reverse-DNS",
                False,
            )

        time_related = any(
            cls._time_gap(query_time, target_time) <= cls.RELATION_WINDOW_SECONDS
            for query_time in query_times
            for target_time in target_times
        )
        if time_related:
            return (
                "external_candidate",
                "Внешний кандидат — DNS-запрос в пределах 5 секунд; "
                "связь не подтверждена",
                False,
            )
        return (
            "background",
            "Фоновый DNS-запрос — близкой временной связи с целевым сайтом нет",
            False,
        )

    @classmethod
    def _is_target_site(cls, hostname: str, site_domain: str) -> bool:
        return hostname == site_domain or hostname.endswith("." + site_domain)

    @classmethod
    def _is_brand_alias(cls, hostname: str, site_domain: str) -> bool:
        return any(
            hostname == alias or hostname.endswith("." + alias)
            for alias in cls.KNOWN_BRAND_ALIASES.get(site_domain, ())
        )

    @classmethod
    def _is_windows_connectivity_probe(cls, hostname: str) -> bool:
        return any(
            hostname == suffix or hostname.endswith("." + suffix)
            for suffix in cls.WINDOWS_CONNECTIVITY_SUFFIXES
        )

    @classmethod
    def _is_reverse_dns(cls, hostname: str) -> bool:
        return any(
            hostname == suffix or hostname.endswith("." + suffix)
            for suffix in cls.REVERSE_DNS_SUFFIXES
        )

    @staticmethod
    def _normalize_ipv4_addresses(values: Iterable[str]) -> tuple[str, ...]:
        addresses: set[str] = set()
        for value in values or ():
            try:
                parsed = ip_address(str(value).strip())
            except ValueError:
                continue
            if isinstance(parsed, IPv4Address):
                addresses.add(str(parsed))
        return tuple(sorted(addresses))

    @staticmethod
    def _routing(
        ips: tuple[str, ...],
        direct_ips: set[str],
        covered_by_rule: bool,
    ) -> str:
        if covered_by_rule:
            return "direct"

        if not ips:
            return "unknown"

        direct_count = sum(1 for address in ips if address in direct_ips)

        if direct_count == 0:
            return "vpn"

        if direct_count == len(ips):
            return "direct"

        return "partial"

    @classmethod
    def _relation(
        cls,
        hostname: str,
        site_domain: str,
    ) -> str:
        if hostname == site_domain or hostname.endswith("." + site_domain):
            return "same_site"

        return "external"

    @classmethod
    def _matching_rule(
        cls,
        hostname: str,
        rules: tuple[str, ...],
    ) -> str | None:
        matches = [
            rule
            for rule in rules
            if (hostname == rule or hostname.endswith("." + rule))
        ]

        if not matches:
            return None

        return max(matches, key=len)

    @classmethod
    def is_selectable_now(
        cls,
        *,
        hostname: str,
        site_domain: str,
        ips: Iterable[str],
        direct_ips: Iterable[str],
        direct_rules: Iterable[str],
        synthetic: bool = False,
    ) -> bool:
        hostname = cls._normalize_domain(hostname)
        site_domain = cls._normalize_domain(site_domain)
        normalized_ips = cls._normalize_ipv4_addresses(ips)
        direct_ip_set = {
            str(value).strip() for value in direct_ips if str(value).strip()
        }
        rules = tuple(
            cls._normalize_domain(value) for value in direct_rules if str(value).strip()
        )
        allowed_host = cls._is_target_site(
            hostname, site_domain
        ) or cls._is_brand_alias(hostname, site_domain)
        covered_rule = cls._matching_rule(hostname, rules)
        return bool(
            not synthetic
            and allowed_host
            and normalized_ips
            and not any(ip in direct_ip_set for ip in normalized_ips)
            and covered_rule is None
        )

    @staticmethod
    def _summary(
        resources: list[DependencyResourceAnalysis],
    ) -> DependencyDiagnosticSummary:
        return DependencyDiagnosticSummary(
            observed=len(resources),
            direct=sum(item.routing == "direct" for item in resources),
            vpn=sum(item.routing == "vpn" for item in resources),
            partial=sum(item.routing == "partial" for item in resources),
            unknown=sum(item.routing == "unknown" for item in resources),
            uncovered=sum(not item.covered_by_rule for item in resources),
        )

    @staticmethod
    def _normalize_domain(value: str) -> str:
        value = str(value).strip().lower().rstrip(".")

        if value.startswith("*."):
            value = value[2:]

        if not value or "." not in value:
            raise ValueError(
                "domain must contain at least two labels",
            )

        return value
