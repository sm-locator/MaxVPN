from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.dependencies import get_db
from app.models.user import User
from backend.application.container import build_add_russian_direct_preset_use_case
from backend.application.use_cases.add_russian_direct_preset import (
    AddRussianDirectPresetUseCase,
)
from backend.services.russian_direct_preset import RUSSIAN_DIRECT_PRESET

router = APIRouter(
    prefix="/smart-routing/presets",
    tags=["Smart Routing"],
)


def get_add_russian_direct_preset_use_case(
    db: Session = Depends(get_db),
) -> AddRussianDirectPresetUseCase:
    return build_add_russian_direct_preset_use_case(db)


@router.get("/russia-direct")
def get_russia_direct_preset() -> dict[str, object]:
    return {
        "preset": "russia-direct",
        "total_domains": len(RUSSIAN_DIRECT_PRESET),
        "domains": [entry.domain for entry in RUSSIAN_DIRECT_PRESET],
    }


@router.post("/russia-direct")
def add_russia_direct_preset(
    current_user: User = Depends(get_current_user),
    use_case: AddRussianDirectPresetUseCase = Depends(
        get_add_russian_direct_preset_use_case,
    ),
) -> dict[str, object]:
    result = use_case.execute(current_user.id)

    return {
        "preset": "russia-direct",
        "requested": result.requested,
        "added": result.added,
        "already_present": result.already_present,
        "total_domains": len(RUSSIAN_DIRECT_PRESET),
        "rules": [
            {
                "id": rule.id,
                "target_type": rule.target_type,
                "target": rule.target,
                "action": rule.action,
                "priority": rule.priority,
                "address_family": rule.address_family,
                "enabled": rule.enabled,
            }
            for rule in result.rules
        ],
    }
