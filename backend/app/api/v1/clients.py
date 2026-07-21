from fastapi import APIRouter, Depends, status

from app.api.dependencies import (
    get_wireguard_manager,
    get_wireguard_server_settings,
)
from app.schemas.wireguard_client import ClientCreate, ClientRead
from app.vpn.wireguard.manager import WireGuardManager
from app.vpn.wireguard.server_settings import WireGuardServerSettings

router = APIRouter(
    prefix="/clients",
    tags=["Clients"],
)


@router.post(
    "",
    response_model=ClientRead,
    status_code=status.HTTP_201_CREATED,
)
def create_client(
    data: ClientCreate,
    manager: WireGuardManager = Depends(get_wireguard_manager),
    server_settings: WireGuardServerSettings = Depends(
        get_wireguard_server_settings,
    ),
) -> ClientRead:
    client = manager.create_client(
        client_name=data.client_name,
        server=server_settings,
    )

    return ClientRead.model_validate(client)
