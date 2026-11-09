from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.smart_routing_sync import get_sync_service
from app.auth.dependencies import get_current_user
from app.database.dependencies import get_db
from app.models.smart_routing_rule import SmartRoutingRule
from app.models.user import User
from app.repositories.smart_routing_rule import SmartRoutingRuleRepository
from app.schemas.smart_routing_rule import (
    SmartRoutingRuleCreate,
    SmartRoutingRuleRead,
    SmartRoutingRuleUpdate,
)
from backend.services.smart_routing_sync import SmartRoutingSyncError

router = APIRouter(
    prefix="/smart-routing/rules",
    tags=["Smart Routing"],
)


def get_repository(
    db: Session = Depends(get_db),
) -> SmartRoutingRuleRepository:
    return SmartRoutingRuleRepository(db)


@router.post(
    "",
    response_model=SmartRoutingRuleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_rule(
    data: SmartRoutingRuleCreate,
    current_user: User = Depends(get_current_user),
    repository: SmartRoutingRuleRepository = Depends(get_repository),
) -> SmartRoutingRule:
    rule = SmartRoutingRule(
        user_id=current_user.id,
        **data.model_dump(),
    )

    return repository.create(rule)


@router.post(
    "/{rule_id}/test",
)
def test_rule(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    repository: SmartRoutingRuleRepository = Depends(get_repository),
    sync_service=Depends(get_sync_service),
):
    rule = repository.get_by_id(
        current_user.id,
        rule_id,
    )

    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Smart Routing rule not found",
        )

    try:
        result = sync_service.test_remote_rule(
            target_type=str(rule.target_type),
            target=str(rule.target),
        )
    except SmartRoutingSyncError as exc:
        message = str(exc)

        if message == "brume_routing_rule_not_found":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=message,
        ) from exc

    return {
        "local_rule": {
            "id": int(rule.id),
            "target_type": str(rule.target_type),
            "target": str(rule.target),
            "action": str(rule.action),
            "priority": int(rule.priority),
            "enabled": bool(rule.enabled),
            "comment": str(getattr(rule, "comment", "") or ""),
        },
        "route_test": result,
    }


@router.get(
    "",
    response_model=list[SmartRoutingRuleRead],
)
def list_rules(
    current_user: User = Depends(get_current_user),
    repository: SmartRoutingRuleRepository = Depends(get_repository),
) -> list[SmartRoutingRule]:
    return repository.get_by_user(current_user.id)


@router.get(
    "/{rule_id}",
    response_model=SmartRoutingRuleRead,
)
def get_rule(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    repository: SmartRoutingRuleRepository = Depends(get_repository),
) -> SmartRoutingRule:
    rule = repository.get_by_id(
        current_user.id,
        rule_id,
    )

    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Smart Routing rule not found",
        )

    return rule


@router.patch(
    "/{rule_id}",
    response_model=SmartRoutingRuleRead,
)
def update_rule(
    rule_id: int,
    data: SmartRoutingRuleUpdate,
    current_user: User = Depends(get_current_user),
    repository: SmartRoutingRuleRepository = Depends(get_repository),
) -> SmartRoutingRule:
    rule = repository.get_by_id(
        current_user.id,
        rule_id,
    )

    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Smart Routing rule not found",
        )

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)

    return repository.update(rule)


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_rule(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    repository: SmartRoutingRuleRepository = Depends(get_repository),
) -> None:
    rule = repository.get_by_id(
        current_user.id,
        rule_id,
    )

    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Smart Routing rule not found",
        )

    repository.delete(rule)
