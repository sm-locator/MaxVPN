from functools import lru_cache

from fastapi import APIRouter, Depends

from app.api.v1.smart_routing_apply import get_smart_routing_service
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.schemas.status import ComponentStatus, MaxVPNStatusRead
from backend.application.container import build_check_wireguard_health_use_case
from backend.infrastructure.config.settings import get_settings
from backend.infrastructure.ssh.ssh_remote_command_executor import (
    SSHRemoteCommandExecutor,
)

router = APIRouter(
    prefix="/status",
    tags=["System Status"],
)


@lru_cache(maxsize=1)
def get_wireguard_health_use_case():
    return build_check_wireguard_health_use_case()


def _router_status() -> ComponentStatus:
    try:
        settings = get_settings()

        executor = SSHRemoteCommandExecutor(
            host=settings.ssh_host,
            username=settings.ssh_username,
            private_key_path=settings.ssh_private_key_path,
            port=settings.ssh_port,
        )

        result = executor.run(
            [
                "ip",
                "link",
                "show",
                "dev",
                "br-lan",
            ]
        )

        if result.returncode != 0:
            return ComponentStatus(
                status="disconnected",
                reason="lan_interface_not_found",
            )

        return ComponentStatus(status="connected")

    except Exception as exc:
        return ComponentStatus(
            status="disconnected",
            reason=str(exc),
        )


def _vpn_status() -> ComponentStatus:
    try:
        health = get_wireguard_health_use_case().execute()
        status = health.status.value

        if status == "healthy":
            return ComponentStatus(status="healthy")

        if status == "degraded":
            return ComponentStatus(
                status="degraded",
                reason=health.reason,
            )

        return ComponentStatus(
            status="failed",
            reason=health.reason,
        )

    except Exception as exc:
        return ComponentStatus(
            status="failed",
            reason=str(exc),
        )


def _smart_routing_status() -> ComponentStatus:
    try:
        result = get_smart_routing_service().verify()

        if result.healthy:
            return ComponentStatus(status="healthy")

        return ComponentStatus(
            status="degraded",
            reason=result.reason,
        )

    except Exception as exc:
        return ComponentStatus(
            status="failed",
            reason=str(exc),
        )


@router.get(
    "",
    response_model=MaxVPNStatusRead,
)
def get_status(
    _: User = Depends(get_current_user),
) -> MaxVPNStatusRead:
    return MaxVPNStatusRead(
        router=_router_status(),
        vpn=_vpn_status(),
        smart_routing=_smart_routing_status(),
    )
