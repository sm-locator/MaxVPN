from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.dependencies import get_db
from app.models.smart_routing_dependency_group import (
    SmartRoutingDependencyGroup,
)
from app.models.smart_routing_rule import SmartRoutingRule
from app.models.user import User
from app.repositories.smart_routing_dependency_group import (
    SmartRoutingDependencyGroupRepository,
)
from app.repositories.smart_routing_rule import SmartRoutingRuleRepository

router = APIRouter(
    prefix="/smart-routing/dependency-groups",
    tags=["Smart Routing"],
)


class DependencyGroupCreate(BaseModel):
    site_domain: str = Field(min_length=1, max_length=255)
    title: str | None = Field(default=None, max_length=255)


class DependencyGroupRuleCreate(BaseModel):
    rule_id: int
    source: str = Field(default="diagnostic", min_length=1, max_length=20)


def get_group_repository(
    db: Session = Depends(get_db),
) -> SmartRoutingDependencyGroupRepository:
    return SmartRoutingDependencyGroupRepository(db)


def get_rule_repository(
    db: Session = Depends(get_db),
) -> SmartRoutingRuleRepository:
    return SmartRoutingRuleRepository(db)


def _normalize_domain(value: str) -> str:
    value = value.strip().lower().rstrip("/").rstrip(".")
    if value.startswith("http://"):
        value = "http://" + value[len("http://") :].split("/", 1)[0]
    elif value.startswith("https://"):
        value = "https://" + value[len("https://") :].split("/", 1)[0]
    else:
        if "/" in value:
            value = value.split("/", 1)[0]

    hostname = value
    if "://" in value:
        hostname = value.split("://", 1)[1]

    if not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
        r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+",
        hostname,
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid site domain",
        )

    return value


def _rule_payload(rule: SmartRoutingRule | None) -> dict | None:
    if rule is None:
        return None

    return {
        "id": rule.id,
        "target_type": str(rule.target_type),
        "target": rule.target,
        "action": str(rule.action),
        "priority": rule.priority,
        "address_family": str(rule.address_family),
        "enabled": bool(rule.enabled),
    }


def _group_payload(group: SmartRoutingDependencyGroup) -> dict:
    items = []
    for item in group.items:
        items.append(
            {
                "id": item.id,
                "rule_id": item.rule_id,
                "source": item.source,
                "rule": _rule_payload(item.rule),
            }
        )

    return {
        "id": group.id,
        "site_domain": group.site_domain,
        "title": group.title,
        "items": items,
    }


@router.get("")
def list_dependency_groups(
    current_user: User = Depends(get_current_user),
    repository: SmartRoutingDependencyGroupRepository = Depends(get_group_repository),
) -> list[dict]:
    groups = repository.get_by_user(current_user.id)
    return [_group_payload(group) for group in groups]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
def create_dependency_group(
    data: DependencyGroupCreate,
    current_user: User = Depends(get_current_user),
    repository: SmartRoutingDependencyGroupRepository = Depends(get_group_repository),
) -> dict:
    site_domain = _normalize_domain(data.site_domain)

    group = repository.get_or_create(
        current_user.id,
        site_domain,
        title=(data.title or site_domain).strip() or site_domain,
    )

    return _group_payload(group)


@router.post("/{group_id}/rules")
def add_rule_to_dependency_group(
    group_id: int,
    data: DependencyGroupRuleCreate,
    current_user: User = Depends(get_current_user),
    group_repository: SmartRoutingDependencyGroupRepository = Depends(
        get_group_repository
    ),
    rule_repository: SmartRoutingRuleRepository = Depends(get_rule_repository),
) -> dict:
    group = _find_group(
        group_repository,
        current_user.id,
        group_id,
    )
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dependency group not found",
        )

    rule = rule_repository.get_by_id(
        current_user.id,
        data.rule_id,
    )
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Smart Routing rule not found",
        )

    group_repository.add_rule(
        group,
        rule.id,
        source=data.source.strip().lower() or "diagnostic",
    )

    return _group_payload(group)


@router.delete("/{group_id}/rules/{rule_id}")
def remove_rule_from_dependency_group(
    group_id: int,
    rule_id: int,
    current_user: User = Depends(get_current_user),
    group_repository: SmartRoutingDependencyGroupRepository = Depends(
        get_group_repository
    ),
) -> dict:
    group = _find_group(group_repository, current_user.id, group_id)

    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dependency group not found",
        )

    group_repository.remove_rule(group, rule_id)

    return _group_payload(group)


def _find_group(
    repository: SmartRoutingDependencyGroupRepository,
    user_id: int,
    group_id: int,
) -> SmartRoutingDependencyGroup | None:
    groups = repository.get_by_user(user_id)
    for group in groups:
        if group.id == group_id:
            return group
    return None


def _group_domain_for_id(
    repository: SmartRoutingDependencyGroupRepository,
    user_id: int,
    group_id: int,
) -> str:
    group = _find_group(repository, user_id, group_id)
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dependency group not found",
        )
    return group.site_domain
