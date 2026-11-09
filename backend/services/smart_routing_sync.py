from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from ipaddress import ip_network
from pathlib import Path
from typing import Any

from backend.models.smart_routing_rule_data import SmartRoutingRuleData
from backend.ports.remote_command_executor import RemoteCommandExecutor


class SmartRoutingSyncError(RuntimeError):
    """Raised when Smart Routing synchronization cannot be completed."""


@dataclass(frozen=True, slots=True)
class SmartRoutingSyncResult:
    local_rules: list[dict[str, Any]]
    remote_rules: list[dict[str, Any]]
    same: list[dict[str, Any]]
    local_only: list[dict[str, Any]]
    remote_only: list[dict[str, Any]]
    semantic_mismatches: list[dict[str, Any]]
    order_mismatches: list[dict[str, Any]]
    protected_local_only: list[dict[str, Any]]
    unprotected_local_only: list[dict[str, Any]]
    remote_runtime: dict[str, Any]
    remote_fingerprint: str
    diagnostic_relinks: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "local": {
                "total": len(self.local_rules),
                "rules": self.local_rules,
            },
            "remote": {
                "total": len(self.remote_rules),
                "rules": self.remote_rules,
                "runtime": self.remote_runtime,
                "fingerprint": self.remote_fingerprint,
            },
            "diff": {
                "same": self.same,
                "local_only": self.local_only,
                "remote_only": self.remote_only,
                "semantic_mismatches": self.semantic_mismatches,
                "order_mismatches": self.order_mismatches,
                "protected_local_only": self.protected_local_only,
                "unprotected_local_only": self.unprotected_local_only,
                "diagnostic_relinks": self.diagnostic_relinks,
            },
        }


class SmartRoutingSyncService:
    """
    Read-only comparison and safe additive Pull between local MaxVPN
    Smart Routing rules and the Brume 3 appliance.

    Absolute priority values are not compared because localhost and the
    appliance intentionally use different priority ranges.

    Pull is additive:
    - common rules are not modified;
    - local-only rules are never deleted;
    - remote-only rules are imported with locally allocated priorities;
    - existing diagnostic/static local rules are therefore preserved.
    """

    REMOTE_URL = "http://127.0.0.1:8787/api/appliance/v1/routing"

    def __init__(
        self,
        executor: RemoteCommandExecutor,
        russian_direct_file: Path,
    ) -> None:
        self._executor = executor
        self._russian_direct_domains = self._load_russian_direct_domains(
            russian_direct_file
        )

    def fetch_remote_state(self) -> dict[str, Any]:
        command = ["curl", "-fsS", self.REMOTE_URL]
        result = self._executor.run(command)

        # Only this operation is retried: it is a read-only GET from the appliance.
        # Do not retry mutations at the SSH-executor level because a remote command
        # could have completed before the transport closed.
        transient_markers = (
            "connection closed by",
            "connection reset by",
            "connection timed out",
            "broken pipe",
        )
        detail = (result.stderr or "").lower()
        if result.returncode != 0 and any(
            marker in detail for marker in transient_markers
        ):
            time.sleep(0.2)
            result = self._executor.run(command)

        if result.returncode != 0:
            detail = result.stderr or "remote command failed"
            raise SmartRoutingSyncError(f"brume_routing_read_failed: {detail}")

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise SmartRoutingSyncError("brume_routing_invalid_json") from exc

        if not isinstance(payload, dict):
            raise SmartRoutingSyncError("brume_routing_invalid_payload")

        rules = payload.get("rules")
        runtime = payload.get("runtime")

        if not isinstance(rules, list):
            raise SmartRoutingSyncError("brume_routing_rules_missing")

        if not isinstance(runtime, dict):
            runtime = {}

        normalized_rules = [self._normalize_remote_rule(rule) for rule in rules]

        # Diagnostic comments describe provenance only; they are not routing
        # semantics and must not make an otherwise identical runtime state
        # appear different.
        fingerprint_rules = [
            {key: value for key, value in rule.items() if key != "comment"}
            for rule in normalized_rules
        ]

        fingerprint_payload = {
            "rules": fingerprint_rules,
            "runtime": runtime,
        }

        canonical = json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        return {
            "rules": normalized_rules,
            "runtime": runtime,
            "fingerprint": fingerprint,
        }

    def test_remote_rule(
        self,
        target_type: str,
        target: str,
    ) -> dict[str, Any]:
        """
        Run the read-only route-test on the matching rule
        currently installed on the Brume 3 appliance.

        The normal sync representation intentionally omits the
        appliance rule id, therefore route-test resolves the raw
        remote rule first and uses its real id.
        """

        normalized_type = str(target_type or "").strip().lower()

        normalized_target = self._normalize_target(
            normalized_type,
            str(target or ""),
        )

        response = self._executor.run(
            [
                "curl",
                "-fsS",
                self.REMOTE_URL,
            ],
        )

        if response.returncode != 0:
            detail = response.stderr or response.stdout or "remote routing read failed"
            raise SmartRoutingSyncError(f"brume_routing_read_failed: {detail}")

        try:
            payload = json.loads(response.stdout)
        except json.JSONDecodeError as exc:
            raise SmartRoutingSyncError("brume_routing_invalid_json") from exc

        if not isinstance(payload, dict):
            raise SmartRoutingSyncError("brume_routing_invalid_payload")

        remote_rules = payload.get("rules")

        if not isinstance(remote_rules, list):
            raise SmartRoutingSyncError("brume_routing_rules_missing")

        matching_rule = None

        for remote_rule in remote_rules:
            if not isinstance(
                remote_rule,
                dict,
            ):
                continue

            remote_type = (
                str(
                    remote_rule.get(
                        "target_type",
                        "",
                    )
                )
                .strip()
                .lower()
            )

            try:
                remote_target = self._normalize_target(
                    remote_type,
                    str(
                        remote_rule.get(
                            "target",
                            "",
                        )
                    ),
                )
            except SmartRoutingSyncError:
                continue

            if remote_type == normalized_type and remote_target == normalized_target:
                matching_rule = remote_rule
                break

        if matching_rule is None:
            raise SmartRoutingSyncError("brume_routing_rule_not_found")

        remote_id = matching_rule.get("id")

        if remote_id is None:
            raise SmartRoutingSyncError("brume_routing_rule_id_missing")

        try:
            remote_id = int(remote_id)
        except (TypeError, ValueError) as exc:
            raise SmartRoutingSyncError("brume_routing_rule_id_invalid") from exc

        test_response = self._executor.run(
            [
                "curl",
                "-fsS",
                "-X",
                "POST",
                "-H",
                "Content-Type: application/json",
                "-d",
                "{}",
                f"{self.REMOTE_URL}/rules/{remote_id}/test",
            ],
        )

        if test_response.returncode != 0:
            detail = (
                test_response.stderr
                or test_response.stdout
                or "remote route-test failed"
            )
            raise SmartRoutingSyncError(f"brume_routing_route_test_failed: {detail}")

        try:
            result = json.loads(test_response.stdout)
        except json.JSONDecodeError as exc:
            raise SmartRoutingSyncError(
                "brume_routing_route_test_invalid_json"
            ) from exc

        if not isinstance(result, dict):
            raise SmartRoutingSyncError("brume_routing_route_test_invalid_payload")

        return {
            **result,
            "remote_rule_id": remote_id,
            "remote_rule": {
                key: matching_rule.get(key)
                for key in (
                    "id",
                    "target_type",
                    "target",
                    "action",
                    "priority",
                    "address_family",
                    "enabled",
                    "comment",
                )
                if key in matching_rule
            },
        }

    def preview(
        self,
        local_rules: list[SmartRoutingRuleData],
        protected_local_keys: (
            set[tuple[str, str]] | frozenset[tuple[str, str]]
        ) = frozenset(),
    ) -> SmartRoutingSyncResult:
        remote_state = self.fetch_remote_state()

        return self.preview_from_state(
            local_rules,
            remote_state,
            protected_local_keys=protected_local_keys,
        )

    def preview_from_state(
        self,
        local_rules: list[SmartRoutingRuleData],
        remote_state: dict[str, Any],
        protected_local_keys: (
            set[tuple[str, str]] | frozenset[tuple[str, str]]
        ) = frozenset(),
    ) -> SmartRoutingSyncResult:
        local = [self._normalize_local_rule(rule) for rule in local_rules]

        remote = list(remote_state["rules"])

        local_by_key = {self._identity(rule): rule for rule in local}

        remote_by_key = {self._identity(rule): rule for rule in remote}

        same: list[dict[str, Any]] = []
        local_only: list[dict[str, Any]] = []
        remote_only: list[dict[str, Any]] = []
        semantic_mismatches: list[dict[str, Any]] = []
        diagnostic_relinks: list[dict[str, Any]] = []

        for key, local_rule in local_by_key.items():
            remote_rule = remote_by_key.get(key)

            if remote_rule is None:
                local_only.append(local_rule)
                continue

            if self._semantic_signature(local_rule) == self._semantic_signature(
                remote_rule
            ):
                same.append(local_rule)
            else:
                semantic_mismatches.append(
                    {
                        "target_type": local_rule["target_type"],
                        "target": local_rule["target"],
                        "local": local_rule,
                        "remote": remote_rule,
                    }
                )

        for key, remote_rule in remote_by_key.items():
            if key not in local_by_key:
                remote_only.append(remote_rule)

        # A diagnostic rule can already exist in localhost while its
        # dependency-group relation is missing (for example after an older
        # sync implementation imported it as a normal custom exception).
        # The appliance carries its provenance in the diagnostic comment.
        diagnostic_relinks = [
            remote_rule
            for remote_rule in remote
            if (
                self.diagnostic_site_from_comment(remote_rule.get("comment"))
                and self._identity(remote_rule) in local_by_key
                and self._identity(remote_rule) not in protected_local_keys
            )
        ]

        # Absolute priority/order is intentionally not compared.
        #
        # localhost and Brume use different priority ranges.
        # The appliance also separates domain and CIDR rules when
        # constructing runtime routing state. Therefore different
        # ordering between these rule classes is not a synchronization
        # conflict.
        #
        # Actual logical conflicts are detected above using rule identity
        # and semantic parameters.
        order_mismatches: list[dict[str, Any]] = []

        protected_targets = {
            self._identity(rule)
            for rule in local_only
            if (
                self._identity(rule) in protected_local_keys
                or (rule["target_type"] == "cidr" and rule["action"] == "direct")
            )
        }

        protected_local_only = [
            rule for rule in local_only if self._identity(rule) in protected_targets
        ]

        unprotected_local_only = [
            rule for rule in local_only if self._identity(rule) not in protected_targets
        ]

        return SmartRoutingSyncResult(
            local_rules=[self._public_rule(rule) for rule in local],
            remote_rules=[self._public_rule(rule) for rule in remote],
            same=[self._public_rule(rule) for rule in same],
            local_only=[self._public_rule(rule) for rule in local_only],
            remote_only=[self._public_rule(rule) for rule in remote_only],
            semantic_mismatches=[
                self._public_mismatch(item) for item in semantic_mismatches
            ],
            order_mismatches=order_mismatches,
            protected_local_only=[
                self._public_rule(rule) for rule in protected_local_only
            ],
            unprotected_local_only=[
                self._public_rule(rule) for rule in unprotected_local_only
            ],
            remote_runtime=dict(remote_state["runtime"]),
            diagnostic_relinks=[self._public_rule(rule) for rule in diagnostic_relinks],
            remote_fingerprint=str(remote_state["fingerprint"]),
        )

    def build_pull_plan(
        self,
        local_rules: list[SmartRoutingRuleData],
        protected_local_keys: (
            set[tuple[str, str]] | frozenset[tuple[str, str]]
        ) = frozenset(),
    ) -> tuple[SmartRoutingSyncResult, list[dict[str, Any]]]:
        remote_state = self.fetch_remote_state()

        result = self.preview_from_state(
            local_rules,
            remote_state,
            protected_local_keys=protected_local_keys,
        )

        if result.semantic_mismatches:
            raise SmartRoutingSyncError("brume_routing_semantic_conflict")

        if result.order_mismatches:
            raise SmartRoutingSyncError("brume_routing_order_conflict")

        imports = self.allocate_local_priorities(
            local_rules,
            result.remote_only,
        )

        return result, imports

    def allocate_local_priorities(
        self,
        local_rules: list[SmartRoutingRuleData],
        remote_only: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        used_priorities = {int(rule.priority) for rule in local_rules}

        local_rule_dicts = [self._normalize_local_rule(rule) for rule in local_rules]

        russian_priorities = [
            int(rule["priority"])
            for rule in local_rule_dicts
            if self.is_russian_direct(
                rule["target_type"],
                rule["target"],
            )
        ]

        next_russian = (max(russian_priorities) if russian_priorities else 0) + 1

        next_custom = (max(used_priorities) if used_priorities else 0) + 10

        planned: list[dict[str, Any]] = []

        for remote_rule in remote_only:
            self._validate_pull_rule(remote_rule)

            if self.is_russian_direct(
                remote_rule["target_type"],
                remote_rule["target"],
            ):
                priority = next_russian

                while priority in used_priorities:
                    priority += 1

                next_russian = priority + 1
            else:
                priority = next_custom

                while priority in used_priorities:
                    priority += 10

                next_custom = priority + 10

            used_priorities.add(priority)

            planned.append(
                {
                    **remote_rule,
                    "local_priority": priority,
                }
            )

        return planned

    def push_local_only(
        self,
        local_rules: list[SmartRoutingRuleData],
        *,
        expected_remote_fingerprint: str | None = None,
        protected_local_keys: (
            set[tuple[str, str]] | frozenset[tuple[str, str]]
        ) = frozenset(),
        diagnostic_comments: dict[tuple[str, str], str] | None = None,
    ) -> dict[str, Any]:
        """
        Add local-only rules to the Brume appliance.

        This operation is deliberately additive:
        - no remote rule is deleted;
        - no existing remote rule is modified;
        - runtime is not applied automatically;
        - the caller may provide an expected fingerprint to prevent
          writing against a stale remote preview.
        """
        remote_state = self.fetch_remote_state()

        actual_fingerprint = str(remote_state["fingerprint"])

        if (
            expected_remote_fingerprint is not None
            and expected_remote_fingerprint != actual_fingerprint
        ):
            raise SmartRoutingSyncError("remote_state_changed")

        preview = self.preview_from_state(
            local_rules,
            remote_state,
            protected_local_keys=protected_local_keys,
        )

        if preview.semantic_mismatches:
            raise SmartRoutingSyncError("brume_routing_semantic_conflict")

        if preview.order_mismatches:
            raise SmartRoutingSyncError("brume_routing_order_conflict")

        local_only = sorted(
            preview.local_only,
            key=lambda rule: (
                int(rule["priority"]),
                str(rule["target"]),
            ),
        )

        if not local_only:
            return {
                "pushed": False,
                "reason": "already_up_to_date",
                "created": [],
                "remote_total": len(remote_state["rules"]),
                "remote_fingerprint": actual_fingerprint,
                "apply_required": False,
            }

        for rule in local_only:
            self._validate_push_rule(rule)

        remote_priorities = {int(rule["priority"]) for rule in remote_state["rules"]}

        next_priority = max(remote_priorities, default=0) + 10

        created: list[dict[str, Any]] = []

        for rule in local_only:
            while next_priority in remote_priorities:
                next_priority += 10

            rule_identity = self.identity_from_values(
                str(rule["target_type"]),
                str(rule["target"]),
            )
            diagnostic_comment = (diagnostic_comments or {}).get(rule_identity)
            payload = {
                "target_type": rule["target_type"],
                "target": rule["target"],
                "comment": diagnostic_comment or "MaxVPN sync: imported from localhost",
            }

            response = self._executor.run(
                [
                    "curl",
                    "-fsS",
                    "-X",
                    "POST",
                    "-H",
                    "Content-Type: application/json",
                    "--data-binary",
                    "@-",
                    f"{self.REMOTE_URL}/rules",
                ],
                stdin=json.dumps(
                    payload,
                    ensure_ascii=False,
                ),
            )

            if response.returncode != 0:
                detail = response.stderr or response.stdout or "remote push failed"

                raise SmartRoutingSyncError(f"brume_routing_push_failed: {detail}")

            try:
                created_rule = json.loads(response.stdout)
            except json.JSONDecodeError as exc:
                raise SmartRoutingSyncError("brume_routing_push_invalid_json") from exc

            if not isinstance(created_rule, dict):
                raise SmartRoutingSyncError("brume_routing_push_invalid_payload")

            created.append(created_rule)
            remote_priorities.add(next_priority)
            next_priority += 10

        final_state = self.fetch_remote_state()

        return {
            "pushed": True,
            "created": created,
            "created_count": len(created),
            "remote_total": len(final_state["rules"]),
            "remote_fingerprint": final_state["fingerprint"],
            "apply_required": True,
        }

    @staticmethod
    def _validate_push_rule(
        rule: dict[str, Any],
    ) -> None:
        if rule["action"] != "direct":
            raise SmartRoutingSyncError("brume_routing_unsupported_action")

        if not rule["enabled"]:
            raise SmartRoutingSyncError("brume_routing_disabled_push_not_supported")

        if rule["target_type"] not in {
            "domain",
            "cidr",
        }:
            raise SmartRoutingSyncError("brume_routing_unsupported_target_type")

        if rule["target_type"] == "cidr" and ":" in rule["target"]:
            raise SmartRoutingSyncError("brume_routing_ipv6_cidr_push_not_supported")

    def is_russian_direct(
        self,
        target_type: str,
        target: str,
    ) -> bool:
        if target_type != "domain":
            return False

        return (
            self._normalize_target(target_type, target) in self._russian_direct_domains
        )

    @staticmethod
    def identity_from_values(
        target_type: str,
        target: str,
    ) -> tuple[str, str]:
        return (
            str(target_type),
            SmartRoutingSyncService._normalize_target(
                str(target_type),
                str(target),
            ),
        )

    @staticmethod
    def _identity(
        rule: dict[str, Any],
    ) -> tuple[str, str]:
        return SmartRoutingSyncService.identity_from_values(
            str(rule["target_type"]),
            str(rule["target"]),
        )

    @staticmethod
    def _semantic_signature(
        rule: dict[str, Any] | None,
    ) -> tuple[str, str, str, bool] | None:
        if rule is None:
            return None

        return (
            str(rule["action"]),
            str(rule["address_family"]),
            str(rule["target_type"]),
            bool(rule["enabled"]),
        )

    @staticmethod
    def _normalize_local_rule(
        rule: SmartRoutingRuleData,
    ) -> dict[str, Any]:
        return {
            "target_type": str(rule.target_type),
            "target": SmartRoutingSyncService._normalize_target(
                str(rule.target_type),
                str(rule.target),
            ),
            "action": str(rule.action),
            "priority": int(rule.priority),
            "address_family": str(rule.address_family),
            "enabled": bool(rule.enabled),
        }

    @staticmethod
    def _normalize_remote_rule(
        rule: Any,
    ) -> dict[str, Any]:
        if not isinstance(rule, dict):
            raise SmartRoutingSyncError("brume_routing_invalid_rule")

        required = (
            "target_type",
            "target",
            "action",
            "priority",
            "address_family",
            "enabled",
        )

        if any(field not in rule for field in required):
            raise SmartRoutingSyncError("brume_routing_rule_fields_missing")

        target_type = str(rule["target_type"])

        return {
            "target_type": target_type,
            "target": SmartRoutingSyncService._normalize_target(
                target_type,
                str(rule["target"]),
            ),
            "action": str(rule["action"]),
            "priority": int(rule["priority"]),
            "address_family": str(rule["address_family"]),
            "enabled": bool(rule["enabled"]),
            "comment": str(rule.get("comment") or "").strip(),
        }

    @staticmethod
    def diagnostic_site_from_comment(comment: str | None) -> str | None:
        value = str(comment or "").strip()
        match = re.match(
            r"^Диагностика\s*:\s*(.+)$",
            value,
            re.IGNORECASE,
        )
        if not match:
            return None

        site = match.group(1).strip().lower().rstrip(".")
        return site or None

    @staticmethod
    def _normalize_target(
        target_type: str,
        target: str,
    ) -> str:
        value = target.strip().lower()

        if target_type == "domain":
            return value.rstrip(".")

        if target_type == "cidr":
            try:
                return str(ip_network(value, strict=False))
            except ValueError as exc:
                raise SmartRoutingSyncError(f"invalid_cidr_target: {target}") from exc

        return value

    @staticmethod
    def _public_rule(
        rule: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if rule is None:
            return None

        return {key: value for key, value in rule.items() if not key.startswith("_")}

    @classmethod
    def _public_mismatch(
        cls,
        mismatch: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "target_type": mismatch["target_type"],
            "target": mismatch["target"],
            "local": cls._public_rule(mismatch["local"]),
            "remote": cls._public_rule(mismatch["remote"]),
        }

    @staticmethod
    def _validate_pull_rule(
        rule: dict[str, Any],
    ) -> None:
        if rule["action"] != "direct":
            raise SmartRoutingSyncError(
                f"brume_routing_unsupported_action: {rule['action']}"
            )

        if rule["target_type"] not in {"domain", "cidr"}:
            raise SmartRoutingSyncError(
                f"brume_routing_unsupported_target_type: {rule['target_type']}"
            )

        if rule["target_type"] == "cidr" and ":" in rule["target"]:
            raise SmartRoutingSyncError("brume_routing_ipv6_cidr_pull_not_supported")

    @staticmethod
    def _load_russian_direct_domains(
        path: Path,
    ) -> frozenset[str]:
        domains = {
            line.strip().lower().rstrip(".")
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }

        return frozenset(domains)
