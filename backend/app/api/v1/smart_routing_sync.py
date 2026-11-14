from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_role
from app.database.dependencies import get_db
from app.models.roles import UserRole
from app.models.smart_routing_rule import SmartRoutingRule
from app.models.user import User
from app.repositories.smart_routing_dependency_group import (
    SmartRoutingDependencyGroupRepository,
)
from app.repositories.smart_routing_rule import SmartRoutingRuleRepository
from backend.infrastructure.config.settings import get_settings
from backend.infrastructure.ssh.ssh_remote_command_executor import (
    SSHRemoteCommandExecutor,
)
from backend.models.smart_routing_rule_data import SmartRoutingRuleData
from backend.services.smart_routing_sync import (
    SmartRoutingSyncError,
    SmartRoutingSyncService,
)

router = APIRouter(
    prefix="/smart-routing/sync",
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    tags=["Smart Routing"],
)


class SmartRoutingSyncPushRequest(BaseModel):
    confirm: bool = False
    expected_remote_fingerprint: str | None = None


class SmartRoutingSyncPullRequest(BaseModel):
    confirm: bool = False
    expected_remote_fingerprint: str | None = None


@lru_cache(maxsize=1)
def get_sync_service() -> SmartRoutingSyncService:
    settings = get_settings()

    executor = SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
        timeout=15,
    )

    russian_direct_file = (
        Path(__file__).resolve().parents[3]
        / "data"
        / "smart-routing"
        / "russia-direct.txt"
    )

    return SmartRoutingSyncService(
        executor=executor,
        russian_direct_file=russian_direct_file,
    )


def _rule_data(rule: SmartRoutingRule) -> SmartRoutingRuleData:
    return SmartRoutingRuleData(
        target_type=rule.target_type,
        target=rule.target,
        action=rule.action,
        priority=int(rule.priority),
        address_family=rule.address_family,
        enabled=bool(rule.enabled),
    )


def _get_local_context(
    current_user: User,
    db: Session,
):
    rule_repository = SmartRoutingRuleRepository(db)
    group_repository = SmartRoutingDependencyGroupRepository(db)

    rules = rule_repository.get_by_user(current_user.id)
    groups = group_repository.get_by_user(current_user.id)

    local_rules = [_rule_data(rule) for rule in rules]

    protected_local_keys = {
        (
            item.rule.target_type,
            item.rule.target,
        )
        for group in groups
        for item in group.items
        if item.rule is not None
    }

    return rules, local_rules, protected_local_keys


@router.get("")
def preview_smart_routing_sync(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: SmartRoutingSyncService = Depends(get_sync_service),
) -> dict:
    _, local_rules, protected_local_keys = _get_local_context(
        current_user,
        db,
    )

    try:
        return service.preview(
            local_rules,
            protected_local_keys=protected_local_keys,
        ).to_dict()
    except SmartRoutingSyncError as exc:
        # This endpoint is a read-only comparison. A transient router/SSH
        # failure is an upstream error, not an unhandled application error.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="smart_routing_remote_unavailable",
        ) from exc


@router.post("/enabled-from-brume")
def sync_smart_routing_enabled_from_brume(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: SmartRoutingSyncService = Depends(get_sync_service),
) -> dict:
    """
    Fast state-only synchronization:

    Brume 3 -> localhost
    Only the enabled flag is synchronized.

    Existing local rules are matched by:
    target_type + normalized target.

    No rule is created or deleted and no other rule field
    is modified.
    """

    rule_repository = SmartRoutingRuleRepository(db)
    local_rules = rule_repository.get_by_user(current_user.id)

    try:
        remote_state = service.fetch_remote_state()
    except SmartRoutingSyncError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    remote_by_key: dict[
        tuple[str, str],
        dict,
    ] = {}

    for remote_rule in remote_state["rules"]:
        key = service.identity_from_values(
            str(remote_rule["target_type"]),
            str(remote_rule["target"]),
        )

        remote_by_key[key] = remote_rule

    matched_count = 0
    updated_count = 0
    unchanged_count = 0

    try:
        for local_rule in local_rules:
            key = service.identity_from_values(
                str(local_rule.target_type),
                str(local_rule.target),
            )

            remote_rule = remote_by_key.pop(key, None)

            if remote_rule is None:
                continue

            matched_count += 1

            remote_enabled = bool(remote_rule["enabled"])

            local_enabled = bool(local_rule.enabled)

            if local_enabled == remote_enabled:
                unchanged_count += 1
                continue

            local_rule.enabled = remote_enabled
            updated_count += 1

        if updated_count:
            db.commit()

    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="smart_routing_enabled_sync_failed",
        ) from exc

    return {
        "synced": True,
        "updated_count": updated_count,
        "unchanged_count": unchanged_count,
        "matched_count": matched_count,
        "remote_only_count": len(remote_by_key),
        "remote_total": len(remote_state["rules"]),
        "remote_fingerprint": str(remote_state["fingerprint"]),
    }


@router.post("/push")
def push_smart_routing_to_brume(
    data: SmartRoutingSyncPushRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: SmartRoutingSyncService = Depends(get_sync_service),
) -> dict:
    if not data.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="push_confirmation_required",
        )

    rules, local_rules, protected_local_keys = _get_local_context(
        current_user,
        db,
    )

    diagnostic_comments: dict[tuple[str, str], str] = {}
    group_repository = SmartRoutingDependencyGroupRepository(db)
    for group in group_repository.get_by_user(current_user.id):
        site_domain = str(group.site_domain).strip().lower().rstrip(".")
        if not site_domain:
            continue
        diagnostic_comment = f"Диагностика: {site_domain}"
        for item in group.items:
            linked_rule = item.rule
            if linked_rule is None:
                continue
            identity = service.identity_from_values(
                str(linked_rule.target_type),
                str(linked_rule.target),
            )
            # A rule may belong to more than one group. Preserve one stable,
            # deterministic origin rather than silently overwriting it later.
            diagnostic_comments.setdefault(identity, diagnostic_comment)

    try:
        result = service.push_local_only(
            local_rules,
            expected_remote_fingerprint=data.expected_remote_fingerprint,
            protected_local_keys=protected_local_keys,
            diagnostic_comments=diagnostic_comments,
        )
    except SmartRoutingSyncError as exc:
        message = str(exc)

        if message == "remote_state_changed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "remote_state_changed",
                },
            ) from exc

        if message == "brume_routing_semantic_conflict":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": message,
                },
            ) from exc

        if message == "brume_routing_order_conflict":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": message,
                },
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=message,
        ) from exc

    result["local_total"] = len(rules)
    return result


@router.post("/pull")
def pull_smart_routing_from_brume(
    data: SmartRoutingSyncPullRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: SmartRoutingSyncService = Depends(get_sync_service),
) -> dict:
    if not data.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pull_confirmation_required",
        )

    rules, local_rules, protected_local_keys = _get_local_context(
        current_user,
        db,
    )
    group_repository = SmartRoutingDependencyGroupRepository(db)

    try:
        preview, imports = service.build_pull_plan(
            local_rules,
            protected_local_keys=protected_local_keys,
        )
    except SmartRoutingSyncError as exc:
        message = str(exc)

        if message == "brume_routing_semantic_conflict":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": message,
                    "diff": "semantic_mismatch",
                },
            ) from exc

        if message == "brume_routing_order_conflict":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": message,
                    "diff": "order_mismatch",
                },
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=message,
        ) from exc

    if (
        data.expected_remote_fingerprint is not None
        and data.expected_remote_fingerprint != preview.remote_fingerprint
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "remote_state_changed",
                "expected": data.expected_remote_fingerprint,
                "actual": preview.remote_fingerprint,
            },
        )

    if not imports and not preview.diagnostic_relinks:
        return {
            "pulled": False,
            "reason": "already_up_to_date",
            "created": [],
            "created_count": 0,
            "relinked": [],
            "relinked_count": 0,
            "preserved_local_only": preview.protected_local_only,
            "unprotected_local_only": preview.unprotected_local_only,
            "remote_fingerprint": preview.remote_fingerprint,
            "local_total": len(rules),
            "remote_total": len(preview.remote_rules),
            "apply_required": False,
        }

    created: list[dict] = []
    relinked: list[dict] = []

    local_rules_by_key = {
        SmartRoutingSyncService.identity_from_values(
            str(rule.target_type),
            str(rule.target),
        ): rule
        for rule in rules
    }

    try:
        # Repair diagnostic group associations for rules that were previously
        # imported into localhost without their dependency-group relation.
        for remote_rule in preview.diagnostic_relinks:
            diagnostic_site = service.diagnostic_site_from_comment(
                remote_rule.get("comment")
            )
            if not diagnostic_site:
                continue

            key = SmartRoutingSyncService.identity_from_values(
                str(remote_rule["target_type"]),
                str(remote_rule["target"]),
            )
            local_rule = local_rules_by_key.get(key)
            if local_rule is None:
                continue

            group = group_repository.get_or_create(
                current_user.id,
                diagnostic_site,
                title=diagnostic_site,
            )
            group_repository.add_rule(
                group,
                local_rule.id,
                source="brume_sync",
            )
            relinked.append(
                {
                    "id": local_rule.id,
                    "target_type": str(local_rule.target_type),
                    "target": local_rule.target,
                    "group_domain": diagnostic_site,
                }
            )

        for item in imports:
            rule = SmartRoutingRule(
                user_id=current_user.id,
                target_type=item["target_type"],
                target=item["target"],
                action=item["action"],
                priority=int(item["local_priority"]),
                address_family=item["address_family"],
                enabled=bool(item["enabled"]),
            )

            db.add(rule)
            db.flush()
            local_rules_by_key[
                SmartRoutingSyncService.identity_from_values(
                    str(rule.target_type),
                    str(rule.target),
                )
            ] = rule

            diagnostic_site = service.diagnostic_site_from_comment(item.get("comment"))
            if diagnostic_site:
                group = group_repository.get_or_create(
                    current_user.id,
                    diagnostic_site,
                    title=diagnostic_site,
                )
                group_repository.add_rule(
                    group,
                    rule.id,
                    source="brume_sync",
                )

            created.append(
                {
                    "id": rule.id,
                    "target_type": str(rule.target_type),
                    "target": rule.target,
                    "action": str(rule.action),
                    "priority": rule.priority,
                    "address_family": str(rule.address_family),
                    "enabled": bool(rule.enabled),
                }
            )

        db.commit()

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"smart_routing_pull_failed: {exc}",
        ) from exc

    result = {
        "pulled": bool(created or relinked),
        "created": created,
        "created_count": len(created),
        "relinked": relinked,
        "relinked_count": len(relinked),
        "preserved_local_only": preview.protected_local_only,
        "unprotected_local_only": preview.unprotected_local_only,
        "remote_total": len(preview.remote_rules),
        "local_total_before": len(rules),
        "local_total_after": len(rules) + len(created),
        "remote_fingerprint": preview.remote_fingerprint,
        "apply_required": bool(created),
    }

    if relinked and not created:
        result["reason"] = "diagnostic_groups_repaired"

    return result
