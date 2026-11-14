from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.smart_routing_sync import get_sync_service
from app.auth.dependencies import get_current_user, require_role
from app.database.dependencies import get_db
from app.models.roles import UserRole
from app.models.user import User
from backend.application.container import (
    build_preview_smart_routing_runtime_use_case,
    build_smart_routing_service_from_discovery,
)
from backend.application.use_cases.preview_smart_routing_runtime import (
    PreviewSmartRoutingRuntimeUseCase,
)
from backend.infrastructure.openwrt.openwrt_traffic_routing import (
    OpenWrtTrafficRoutingResult,
)
from backend.services.smart_routing_service import (
    SmartRoutingService,
)
from backend.services.smart_routing_sync import (
    SmartRoutingSyncError,
    SmartRoutingSyncService,
)

router = APIRouter(
    prefix="/smart-routing",
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    tags=["Smart Routing"],
)


@lru_cache(maxsize=1)
def get_smart_routing_service() -> SmartRoutingService:
    return build_smart_routing_service_from_discovery()


class SmartRoutingApplyRequest(BaseModel):
    expected_remote_fingerprint: str | None = None


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
    service: SmartRoutingSyncService = Depends(get_sync_service),
    data: SmartRoutingApplyRequest | None = None,
) -> OpenWrtTrafficRoutingResult:
    try:
        runtime = service.apply_remote_runtime(
            data.expected_remote_fingerprint if data else None
        )
    except SmartRoutingSyncError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
                if str(exc) == "remote_state_changed"
                else status.HTTP_502_BAD_GATEWAY
            ),
            detail=str(exc),
        ) from exc
    counts = [
        runtime.get("mangle_direct_count"),
        runtime.get("mangle_static_count"),
        runtime.get("mangle_static_net_count"),
    ]
    route_ok = "default" in str(runtime.get("table_200", ""))
    ipsets_ok = all(
        runtime.get(key) for key in ("direct_ipset", "static_ipset", "static_net_ipset")
    )
    policy_ok = any(
        "fwmark 0x64/0xff" in line and "lookup 200" in line
        for line in str(runtime.get("ip_rule", "")).splitlines()
    )
    snapshot_ok = bool(runtime.get("config_hash")) and runtime.get(
        "config_hash"
    ) == runtime.get("applied_config_hash")
    healthy = (
        ipsets_ok
        and counts[:2] == [1, 1]
        and counts[2] in (0, 1)
        and route_ok
        and policy_ok
        and snapshot_ok
    )
    if not healthy:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="appliance_runtime_verification_failed",
        )
    return OpenWrtTrafficRoutingResult(
        healthy=healthy,
        direct_ipset_exists=bool(runtime.get("direct_ipset")),
        direct_rule_count=sum(count for count in counts if isinstance(count, int)),
        routing_table_exists=bool(runtime.get("table_200")),
        direct_route_exists=route_ok,
        reason=None if healthy else "appliance_runtime_verification_failed",
    )


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
