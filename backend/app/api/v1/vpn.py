from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.dependencies import get_db
from app.models.user import User
from app.schemas.vpn import (
    VpnProfileApplyResponse,
    VpnProfileConfigResponse,
    VpnProfileConfigUpdate,
    VpnProfileReadResponse,
    VpnProfileUpsert,
    VpnProfileValidateRequest,
    VpnProfileValidationResponse,
    VpnRuntimeModeResponse,
    VpnRuntimeModeUpdate,
    VpnRuntimeResponse,
)
from backend.application.container import (
    build_vless_runtime_service,
    build_vpn_profile_service,
    build_vpn_runtime_service,
)
from backend.services.vpn_profile_service import (
    VpnProfileService,
)
from backend.services.vpn_runtime_service import (
    VpnRuntimeService,
)

router = APIRouter(
    prefix="/vpn",
    tags=["VPN"],
)


def get_vpn_profile_service(
    db: Session = Depends(get_db),
) -> VpnProfileService:
    return build_vpn_profile_service(db)


def get_vpn_runtime_service() -> VpnRuntimeService:
    return build_vpn_runtime_service()


@router.get(
    "/mode",
    response_model=VpnRuntimeModeResponse,
)
def get_runtime_mode(
    current_user: User = Depends(get_current_user),
    service: VpnRuntimeService = Depends(get_vpn_runtime_service),
) -> VpnRuntimeModeResponse:
    try:
        mode = service.get_traffic_mode()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return VpnRuntimeModeResponse(mode=mode, message=f"Текущий режим: {mode}")


@router.post(
    "/mode",
    response_model=VpnRuntimeModeResponse,
)
def set_runtime_mode(
    data: VpnRuntimeModeUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: VpnRuntimeService = Depends(get_vpn_runtime_service),
) -> VpnRuntimeModeResponse:
    try:
        if data.mode == "wan":
            service.stop("WireGuard")
            return VpnRuntimeModeResponse(mode="wan", message="Режим WAN включён")

        if data.mode == "vpn":
            health = service.start("WireGuard")
            if not health.healthy:
                # Revert to WAN if AWG did not pass health verification.
                service.stop("WireGuard")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=health.reason or "vpn_start_verification_failed",
                )
            return VpnRuntimeModeResponse(
                mode="vpn",
                message="Режим AmneziaWG включён",
            )

        vless_service = build_vless_runtime_service(db)
        result = vless_service.enable_lan_routing(current_user.id)
        if not result.get("lan_routing_enabled"):
            raise RuntimeError("vless_lan_routing_verification_failed")
        return VpnRuntimeModeResponse(
            mode="vless",
            message=str(result.get("message") or "Режим VLESS включён"),
        )
    except HTTPException:
        raise
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "/runtime",
    response_model=VpnRuntimeResponse,
)
def get_runtime(
    current_user: User = Depends(get_current_user),
    service: VpnRuntimeService = Depends(get_vpn_runtime_service),
    profile_service: VpnProfileService = Depends(get_vpn_profile_service),
) -> VpnRuntimeResponse:
    try:
        health = service.get_health()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    try:
        traffic_mode = service.get_traffic_mode()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    handshake_age_seconds = service.handshake_age_seconds(
        health,
    )

    try:
        in_sync = profile_service.preflight_apply(
            current_user.id,
            interface="WireGuard",
        )
    except (RuntimeError, LookupError, ValueError):
        in_sync = False

    return VpnRuntimeResponse(
        interface="WireGuard",
        healthy=health.healthy,
        interface_exists=health.interface_exists,
        interface_up=health.interface_up,
        traffic_mode=traffic_mode,
        expected_peer_found=health.expected_peer_found,
        expected_endpoint=health.expected_endpoint,
        endpoint_route_ok=health.endpoint_route_ok,
        listen_port=health.listen_port,
        latest_handshake=health.latest_handshake,
        handshake_age_seconds=handshake_age_seconds,
        rx_bytes=health.rx_bytes,
        tx_bytes=health.tx_bytes,
        reason=health.reason,
        checked_at=health.checked_at,
        in_sync=in_sync,
    )


@router.post(
    "/start",
    response_model=VpnRuntimeResponse,
)
def start_vpn(
    service: VpnRuntimeService = Depends(get_vpn_runtime_service),
) -> VpnRuntimeResponse:
    try:
        health = service.start("WireGuard")
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    if not health.healthy:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=health.reason or "vpn_start_verification_failed",
        )

    return VpnRuntimeResponse(
        interface="WireGuard",
        healthy=health.healthy,
        interface_exists=health.interface_exists,
        interface_up=health.interface_up,
        traffic_mode="vpn",
        expected_peer_found=health.expected_peer_found,
        expected_endpoint=health.expected_endpoint,
        endpoint_route_ok=health.endpoint_route_ok,
        listen_port=health.listen_port,
        latest_handshake=health.latest_handshake,
        handshake_age_seconds=service.handshake_age_seconds(health),
        rx_bytes=health.rx_bytes,
        tx_bytes=health.tx_bytes,
        reason=health.reason,
        checked_at=health.checked_at,
        in_sync=False,
    )


@router.post(
    "/stop",
    response_model=VpnRuntimeResponse,
)
def stop_vpn(
    current_user: User = Depends(get_current_user),
    service: VpnRuntimeService = Depends(get_vpn_runtime_service),
) -> VpnRuntimeResponse:
    try:
        health = service.stop("WireGuard")
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return VpnRuntimeResponse(
        interface="WireGuard",
        healthy=health.healthy,
        interface_exists=health.interface_exists,
        interface_up=health.interface_up,
        traffic_mode="wan",
        expected_peer_found=health.expected_peer_found,
        expected_endpoint=health.expected_endpoint,
        endpoint_route_ok=health.endpoint_route_ok,
        listen_port=health.listen_port,
        latest_handshake=health.latest_handshake,
        handshake_age_seconds=service.handshake_age_seconds(health),
        rx_bytes=health.rx_bytes,
        tx_bytes=health.tx_bytes,
        reason=health.reason,
        checked_at=health.checked_at,
        in_sync=False,
    )


@router.get(
    "/profile",
    response_model=VpnProfileReadResponse | None,
)
def get_profile(
    current_user: User = Depends(get_current_user),
    service: VpnProfileService = Depends(get_vpn_profile_service),
) -> VpnProfileReadResponse | None:
    result = service.get(current_user.id)

    if result is None:
        return None

    return VpnProfileReadResponse(
        id=result.id,
        name=result.name,
        enabled=result.enabled,
        has_private_key=result.has_private_key,
        has_preshared_key=result.has_preshared_key,
    )


@router.get(
    "/profile/config",
    response_model=VpnProfileConfigResponse | None,
)
def get_profile_config(
    current_user: User = Depends(get_current_user),
    service: VpnProfileService = Depends(get_vpn_profile_service),
) -> VpnProfileConfigResponse | None:
    config = service.get_config(current_user.id)

    if config is None:
        return None

    return VpnProfileConfigResponse(
        name=service._repository.get_by_user(current_user.id).name,
        enabled=service._repository.get_by_user(current_user.id).enabled,
        address=config.interface.address,
        dns=config.interface.dns,
        mtu=config.interface.mtu,
        jc=config.interface.jc,
        jmin=config.interface.jmin,
        jmax=config.interface.jmax,
        s1=config.interface.s1,
        s2=config.interface.s2,
        s3=config.interface.s3,
        s4=config.interface.s4,
        h1=config.interface.h1,
        h2=config.interface.h2,
        h3=config.interface.h3,
        h4=config.interface.h4,
        i1=config.interface.i1,
        i2=config.interface.i2,
        i3=config.interface.i3,
        i4=config.interface.i4,
        i5=config.interface.i5,
        public_key=config.peer.public_key,
        allowed_ips=list(config.peer.allowed_ips),
        persistent_keepalive=config.peer.persistent_keepalive,
        endpoint=config.peer.endpoint,
    )


@router.post(
    "/profile/config/validate",
    response_model=VpnProfileValidationResponse,
)
def validate_profile_config(
    data: VpnProfileConfigUpdate,
    current_user: User = Depends(get_current_user),
    service: VpnProfileService = Depends(get_vpn_profile_service),
) -> VpnProfileValidationResponse:
    existing = service.get_config(current_user.id)

    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="vpn_profile_not_found",
        )

    from backend.models.amneziawg_config import (
        AmneziaWGConfig,
        AmneziaWGInterface,
        AmneziaWGPeer,
    )

    config = AmneziaWGConfig(
        interface=AmneziaWGInterface(
            private_key=existing.interface.private_key,
            address=data.address,
            mtu=data.mtu,
            dns=data.dns,
            jc=data.jc,
            jmin=data.jmin,
            jmax=data.jmax,
            s1=data.s1,
            s2=data.s2,
            s3=data.s3,
            s4=data.s4,
            h1=data.h1,
            h2=data.h2,
            h3=data.h3,
            h4=data.h4,
            i1=data.i1,
            i2=data.i2,
            i3=data.i3,
            i4=data.i4,
            i5=data.i5,
        ),
        peer=AmneziaWGPeer(
            public_key=data.public_key,
            allowed_ips=tuple(data.allowed_ips),
            endpoint=data.endpoint,
            persistent_keepalive=data.persistent_keepalive,
            preshared_key=existing.peer.preshared_key,
        ),
    )

    result = service.validate(
        service._renderer.render_full(config),
    )

    return VpnProfileValidationResponse(
        valid=result.valid,
        interface_address=result.interface_address,
        endpoint=result.endpoint,
        allowed_ips=list(result.allowed_ips),
        has_private_key=result.has_private_key,
        has_preshared_key=result.has_preshared_key,
        reason=result.reason,
    )


@router.put(
    "/profile/config",
    response_model=VpnProfileReadResponse,
)
def update_profile_config(
    data: VpnProfileConfigUpdate,
    current_user: User = Depends(get_current_user),
    service: VpnProfileService = Depends(get_vpn_profile_service),
) -> VpnProfileReadResponse:
    existing = service.get_config(current_user.id)

    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="vpn_profile_not_found",
        )

    from backend.models.amneziawg_config import (
        AmneziaWGConfig,
        AmneziaWGInterface,
        AmneziaWGPeer,
    )

    config = AmneziaWGConfig(
        interface=AmneziaWGInterface(
            private_key=existing.interface.private_key,
            address=data.address,
            mtu=data.mtu,
            dns=data.dns,
            jc=data.jc,
            jmin=data.jmin,
            jmax=data.jmax,
            s1=data.s1,
            s2=data.s2,
            s3=data.s3,
            s4=data.s4,
            h1=data.h1,
            h2=data.h2,
            h3=data.h3,
            h4=data.h4,
            i1=data.i1,
            i2=data.i2,
            i3=data.i3,
            i4=data.i4,
            i5=data.i5,
        ),
        peer=AmneziaWGPeer(
            public_key=data.public_key,
            allowed_ips=tuple(data.allowed_ips),
            endpoint=data.endpoint,
            persistent_keepalive=data.persistent_keepalive,
            preshared_key=existing.peer.preshared_key,
        ),
    )

    try:
        result = service.update_config(
            user_id=current_user.id,
            config=config,
            name=data.name,
            enabled=data.enabled,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    read = service.get(current_user.id)

    if read is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="VPN profile could not be loaded after update",
        )

    return VpnProfileReadResponse(
        id=result.id,
        name=read.name,
        enabled=read.enabled,
        has_private_key=read.has_private_key,
        has_preshared_key=read.has_preshared_key,
    )


@router.post(
    "/profile",
    response_model=VpnProfileReadResponse,
)
def save_profile(
    data: VpnProfileUpsert,
    current_user: User = Depends(get_current_user),
    service: VpnProfileService = Depends(get_vpn_profile_service),
) -> VpnProfileReadResponse:
    try:
        service.save(
            user_id=current_user.id,
            name=data.name,
            provider_config=data.provider_config,
            enabled=data.enabled,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    result = service.get(current_user.id)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="VPN profile could not be loaded after save",
        )

    return VpnProfileReadResponse(
        id=result.id,
        name=result.name,
        enabled=result.enabled,
        has_private_key=result.has_private_key,
        has_preshared_key=result.has_preshared_key,
    )


@router.post(
    "/profile/import-current-runtime",
    response_model=VpnProfileReadResponse,
)
def import_current_runtime(
    current_user: User = Depends(get_current_user),
    service: VpnProfileService = Depends(get_vpn_profile_service),
) -> VpnProfileReadResponse:
    try:
        service.import_current_runtime(
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    result = service.get(current_user.id)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="VPN profile could not be loaded after import",
        )

    return VpnProfileReadResponse(
        id=result.id,
        name=result.name,
        enabled=result.enabled,
        has_private_key=result.has_private_key,
        has_preshared_key=result.has_preshared_key,
    )


@router.post(
    "/profile/validate",
    response_model=VpnProfileValidationResponse,
)
def validate_profile(
    data: VpnProfileValidateRequest,
    _: User = Depends(get_current_user),
    service: VpnProfileService = Depends(get_vpn_profile_service),
) -> VpnProfileValidationResponse:
    result = service.validate(data.provider_config)

    return VpnProfileValidationResponse(
        valid=result.valid,
        interface_address=result.interface_address,
        endpoint=result.endpoint,
        allowed_ips=list(result.allowed_ips),
        has_private_key=result.has_private_key,
        has_preshared_key=result.has_preshared_key,
        reason=result.reason,
    )


@router.post(
    "/profile/apply",
    response_model=VpnProfileApplyResponse,
)
def apply_profile(
    current_user: User = Depends(get_current_user),
    service: VpnProfileService = Depends(get_vpn_profile_service),
) -> VpnProfileApplyResponse:
    try:
        result = service.apply(current_user.id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return VpnProfileApplyResponse(
        applied=result.applied,
        verified=result.verified,
        no_change=result.no_change,
        rolled_back=result.rolled_back,
        rollback_verified=result.rollback_verified,
        health_failed=result.health_failed,
        reason=result.reason,
    )
