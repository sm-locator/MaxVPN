from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.dependencies import get_db
from app.models.user import User
from backend.application.container import (
    build_preview_smart_routing_runtime_use_case,
    build_smart_routing_service_from_discovery,
)
from backend.application.use_cases.apply_smart_routing import (
    ApplySmartRoutingUseCase,
)
from backend.application.use_cases.preview_smart_routing_runtime import (
    PreviewSmartRoutingRuntimeUseCase,
)
from backend.infrastructure.openwrt.openwrt_traffic_routing import (
    OpenWrtTrafficRoutingResult,
)
from backend.services.smart_routing_policy_service import (
    SmartRoutingPolicyService,
)
from backend.services.smart_routing_service import (
    SmartRoutingRuntimeCapabilityError,
    SmartRoutingService,
)

router = APIRouter(
    prefix="/smart-routing",
    tags=["Smart Routing"],
)


@lru_cache(maxsize=1)
def get_smart_routing_service() -> SmartRoutingService:
    return build_smart_routing_service_from_discovery()


def get_apply_use_case(
    db: Session = Depends(get_db),
    smart_routing: SmartRoutingService = Depends(get_smart_routing_service),
) -> ApplySmartRoutingUseCase:
    return ApplySmartRoutingUseCase(
        smart_routing=smart_routing,
        policy_service=SmartRoutingPolicyService(db),
    )


def get_preview_smart_routing_runtime_use_case(
    db: Session = Depends(get_db),
) -> PreviewSmartRoutingRuntimeUseCase:
    return build_preview_smart_routing_runtime_use_case(db)


@router.post(
    "/apply",
    response_model=OpenWrtTrafficRoutingResult,
)
def apply_smart_routing(
    current_user: User = Depends(get_current_user),
    use_case: ApplySmartRoutingUseCase = Depends(get_apply_use_case),
) -> OpenWrtTrafficRoutingResult:
    try:
        return use_case.execute_for_user(current_user.id)
    except SmartRoutingRuntimeCapabilityError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get(
    "/runtime-preview",
)
def preview_smart_routing_runtime(
    current_user: User = Depends(get_current_user),
    use_case: PreviewSmartRoutingRuntimeUseCase = Depends(
        get_preview_smart_routing_runtime_use_case,
    ),
) -> dict[str, object]:
    plan = use_case.execute_for_user(current_user.id)

    return {
        "has_changes": plan.has_changes,
        "current": {
            "direct_ipv4_addresses": plan.current.direct_ipv4_addresses,
            "direct_domains": plan.current.direct_domains,
            "rendered_domains": plan.current.rendered_domains,
            "policy_rules": plan.current.policy_rules,
            "routing_table_200": plan.current.routing_table_200,
        },
        "desired": {
            "direct_ipv4_networks": plan.desired.direct_ipv4_networks,
            "direct_domains": plan.desired.direct_domains,
        },
        "diff": {
            "current_ipv4_addresses": plan.diff.current_ipv4_addresses,
            "desired_ipv4_networks": plan.diff.desired_ipv4_networks,
            "covered_ipv4_addresses": plan.diff.covered_ipv4_addresses,
            "stale_ipv4_addresses": plan.diff.stale_ipv4_addresses,
            "ipv4_replace_required": plan.diff.ipv4_replace_required,
            "added_domains": plan.diff.added_domains,
            "removed_domains": plan.diff.removed_domains,
            "unchanged_domains": plan.diff.unchanged_domains,
        },
        "rendered": plan.render(),
    }
