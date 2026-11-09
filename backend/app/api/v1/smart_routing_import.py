from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.dependencies import get_db
from app.models.user import User
from backend.application.use_cases.import_smart_routing import (
    ImportSmartRoutingUseCase,
    SmartRoutingImportPlanItem,
)
from backend.services.smart_routing_import import (
    SmartRoutingImportItem,
    SmartRoutingImportStatus,
    parse_csv_import,
    parse_txt_import,
)

router = APIRouter(
    prefix="/smart-routing/import",
    tags=["Smart Routing"],
)


def _serialize_items(
    items: tuple[SmartRoutingImportPlanItem, ...],
) -> list[dict[str, object]]:
    return [
        {
            "line": item.line,
            "resource": item.resource,
            "target_type": item.target_type,
            "address_family": item.address_family,
            "status": item.status,
            "error": item.error,
        }
        for item in items
    ]


def _parse_content(
    filename: str | None,
    content: bytes,
) -> list[SmartRoutingImportItem]:
    suffix = Path(filename or "").suffix.lower()
    text = content.decode("utf-8-sig")

    if suffix == ".csv":
        return parse_csv_import(text)

    if suffix in {".txt", ""}:
        return parse_txt_import(text)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Поддерживаются только файлы TXT и CSV.",
    )


async def _read_items(
    file: UploadFile,
) -> list[SmartRoutingImportItem]:
    return _parse_content(
        filename=file.filename,
        content=await file.read(),
    )


@router.post(
    "/preview",
    status_code=status.HTTP_200_OK,
)
async def preview_import(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    items = await _read_items(file)

    plan = ImportSmartRoutingUseCase(db).plan(
        user_id=current_user.id,
        items=items,
    )

    return {
        "filename": file.filename,
        "total": len(plan.items),
        "new": len(plan.new_items),
        "duplicates": sum(
            item.status is SmartRoutingImportStatus.DUPLICATE for item in plan.items
        ),
        "already_exists": sum(
            item.status is SmartRoutingImportStatus.ALREADY_EXISTS
            for item in plan.items
        ),
        "invalid": sum(
            item.status is SmartRoutingImportStatus.INVALID for item in plan.items
        ),
        "items": _serialize_items(plan.items),
    }


@router.post(
    "",
    status_code=status.HTTP_200_OK,
)
async def import_rules(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    items = await _read_items(file)

    result = ImportSmartRoutingUseCase(db).execute(
        user_id=current_user.id,
        items=items,
    )

    return {
        "filename": file.filename,
        "requested": result.requested,
        "added": result.added,
        "already_exists": result.already_exists,
        "duplicates": result.duplicates,
        "invalid": result.invalid,
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
