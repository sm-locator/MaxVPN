from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_role
from app.database.dependencies import get_db
from app.models.roles import UserRole
from app.models.user import User
from app.schemas.vless import (
    VlessApplianceKillSwitchUpdateRequest,
    VlessApplianceSyncRequest,
    VlessProfileBatchImportRequest,
    VlessProfileBatchImportResponse,
    VlessProfileDelayResponse,
    VlessProfileEnabledRequest,
    VlessProfileImportRequest,
    VlessProfileReadResponse,
    VlessProfileSelectionRequest,
    VlessProfileValidateRequest,
    VlessProfileValidationResponse,
    VlessRuntimeResponse,
    VlessRuntimeSettingsReadResponse,
    VlessRuntimeSettingsUpdateRequest,
)
from backend.app.schemas.vless import VlessSelectionHistoryResponse
from backend.application.container import (
    build_vless_profile_service,
    build_vless_runtime_service,
)
from backend.services.vless_profile_service import VlessProfileService
from backend.services.vless_runtime_service import VlessRuntimeService

router = APIRouter(prefix="/vless", tags=["VLESS"])


def get_vless_profile_service(db: Session = Depends(get_db)) -> VlessProfileService:
    return build_vless_profile_service(db)


def get_vless_runtime_service(db: Session = Depends(get_db)) -> VlessRuntimeService:
    return build_vless_runtime_service(db)


@router.get("/profile", response_model=VlessProfileReadResponse | None)
def get_profile(
    current_user: User = Depends(get_current_user),
    service: VlessProfileService = Depends(get_vless_profile_service),
) -> VlessProfileReadResponse | None:
    """Backward-compatible endpoint returning the first enabled profile."""
    profile = service.get(current_user.id)
    return VlessProfileReadResponse(**asdict(profile)) if profile else None


@router.get("/profiles", response_model=list[VlessProfileReadResponse])
def list_profiles(
    current_user: User = Depends(get_current_user),
    service: VlessProfileService = Depends(get_vless_profile_service),
) -> list[VlessProfileReadResponse]:
    return [
        VlessProfileReadResponse(**asdict(item))
        for item in service.list(current_user.id)
    ]


@router.get("/profiles/export")
def export_profiles_for_appliance(
    current_user: User = Depends(get_current_user),
    service: VlessProfileService = Depends(get_vless_profile_service),
) -> dict:
    """One-time export of VLESS credentials for migration to maxvpn.lan."""
    return service.export_bundle(current_user.id)


@router.post("/profile/import", response_model=VlessProfileReadResponse)
def import_profile(
    data: VlessProfileImportRequest,
    current_user: User = Depends(get_current_user),
    service: VlessProfileService = Depends(get_vless_profile_service),
) -> VlessProfileReadResponse:
    try:
        profile = service.save(
            user_id=current_user.id,
            source=data.source,
            name=data.name,
            enabled=data.enabled,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return VlessProfileReadResponse(**asdict(profile))


@router.post(
    "/profiles/import-batch",
    response_model=VlessProfileBatchImportResponse,
)
def import_profiles_batch(
    data: VlessProfileBatchImportRequest,
    current_user: User = Depends(get_current_user),
    service: VlessProfileService = Depends(get_vless_profile_service),
) -> VlessProfileBatchImportResponse:
    try:
        result = service.import_many(current_user.id, data.sources)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return VlessProfileBatchImportResponse(**asdict(result))


@router.post("/profile/validate", response_model=VlessProfileValidationResponse)
def validate_profile(
    data: VlessProfileValidateRequest,
    _: User = Depends(get_current_user),
    service: VlessProfileService = Depends(get_vless_profile_service),
) -> VlessProfileValidationResponse:
    return VlessProfileValidationResponse(**asdict(service.validate(data.source)))


@router.patch("/profiles/{profile_id}/enabled", response_model=VlessProfileReadResponse)
def set_profile_enabled(
    profile_id: int,
    data: VlessProfileEnabledRequest,
    current_user: User = Depends(get_current_user),
    service: VlessProfileService = Depends(get_vless_profile_service),
) -> VlessProfileReadResponse:
    try:
        profile = service.set_enabled(current_user.id, profile_id, data.enabled)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return VlessProfileReadResponse(**asdict(profile))


@router.delete("/profiles/{profile_id}", response_model=dict[str, bool])
def delete_profile(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    service: VlessProfileService = Depends(get_vless_profile_service),
) -> dict[str, bool]:
    try:
        service.delete(current_user.id, profile_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return {"deleted": True}


@router.get("/runtime/settings", response_model=VlessRuntimeSettingsReadResponse)
def get_runtime_settings(
    current_user: User = Depends(get_current_user),
    service: VlessProfileService = Depends(get_vless_profile_service),
) -> VlessRuntimeSettingsReadResponse:
    return VlessRuntimeSettingsReadResponse(
        **service.get_runtime_settings(current_user.id)
    )


@router.put("/runtime/settings", response_model=VlessRuntimeSettingsReadResponse)
def update_runtime_settings(
    data: VlessRuntimeSettingsUpdateRequest,
    current_user: User = Depends(get_current_user),
    service: VlessProfileService = Depends(get_vless_profile_service),
) -> VlessRuntimeSettingsReadResponse:
    try:
        result = service.update_runtime_settings(
            current_user.id,
            data.urltest_interval,
            data.urltest_tolerance_ms,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return VlessRuntimeSettingsReadResponse(**result)


@router.get("/runtime", response_model=VlessRuntimeResponse)
def get_runtime(
    current_user: User = Depends(get_current_user),
    service: VlessRuntimeService = Depends(get_vless_runtime_service),
) -> VlessRuntimeResponse:
    try:
        return VlessRuntimeResponse(**service.status(current_user.id))
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.post("/runtime/prepare", response_model=VlessRuntimeResponse)
def prepare_runtime(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    service: VlessRuntimeService = Depends(get_vless_runtime_service),
) -> VlessRuntimeResponse:
    try:
        return VlessRuntimeResponse(**service.prepare(current_user.id))
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.post("/runtime/start", response_model=VlessRuntimeResponse)
def start_runtime(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    service: VlessRuntimeService = Depends(get_vless_runtime_service),
) -> VlessRuntimeResponse:
    try:
        return VlessRuntimeResponse(**service.start(current_user.id))
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.post("/runtime/stop", response_model=VlessRuntimeResponse)
def stop_runtime(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    service: VlessRuntimeService = Depends(get_vless_runtime_service),
) -> VlessRuntimeResponse:
    try:
        return VlessRuntimeResponse(**service.stop(current_user.id))
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.post("/runtime/select", response_model=VlessRuntimeResponse)
def select_runtime_outbound(
    data: VlessProfileSelectionRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    service: VlessRuntimeService = Depends(get_vless_runtime_service),
) -> VlessRuntimeResponse:
    try:
        return VlessRuntimeResponse(
            **service.select_outbound(current_user.id, data.profile_id)
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.get("/appliance-sync/status", response_model=dict[str, Any])
def get_appliance_sync_status(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    service: VlessRuntimeService = Depends(get_vless_runtime_service),
) -> dict[str, Any]:
    """Read maxvpn.lan profile drift and live selection mode
    without modifying the router."""
    try:
        return service.appliance_sync_status(current_user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.put("/appliance/kill-switch", response_model=dict[str, bool])
def set_appliance_kill_switch(
    data: VlessApplianceKillSwitchUpdateRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    service: VlessRuntimeService = Depends(get_vless_runtime_service),
) -> dict[str, bool]:
    try:
        return service.set_appliance_kill_switch(data.enabled)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.post("/appliance-sync", response_model=dict[str, Any])
def synchronize_from_appliance(
    data: VlessApplianceSyncRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    service: VlessRuntimeService = Depends(get_vless_runtime_service),
) -> dict[str, Any]:
    """Pull saved profiles/settings from maxvpn.lan to localhost;
    never applies/restarts sing-box."""
    try:
        return service.synchronize_from_appliance(
            current_user.id,
            confirm_delete_local_only=data.confirm_delete_local_only,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.get("/runtime/selection-history", response_model=VlessSelectionHistoryResponse)
def get_vless_selection_history(
    current_user=Depends(require_role(UserRole.ADMIN)),
    service: VlessRuntimeService = Depends(get_vless_runtime_service),
):
    try:
        return VlessSelectionHistoryResponse(
            **service.get_selection_history(current_user.id)
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.get("/profiles/delays/history", response_model=VlessProfileDelayResponse)
def get_profile_delay_history(
    current_user: User = Depends(get_current_user),
    service: VlessRuntimeService = Depends(get_vless_runtime_service),
) -> VlessProfileDelayResponse:
    try:
        return VlessProfileDelayResponse(
            **service.get_profile_delay_history(current_user.id)
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.get("/profiles/delays", response_model=VlessProfileDelayResponse)
def test_profile_delays(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    service: VlessRuntimeService = Depends(get_vless_runtime_service),
) -> VlessProfileDelayResponse:
    try:
        return VlessProfileDelayResponse(**service.test_profile_delays(current_user.id))
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
