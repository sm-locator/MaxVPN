from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_wireguard_manager
from app.schemas.wireguard_client import ClientCreate, ClientRead
from app.vpn.wireguard.manager import WireGuardManager

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
) -> ClientRead:
    client = manager.create_client(
        client_name=data.client_name,
        dns="1.1.1.1",
        server_public_key="server_public_key",
        endpoint="vpn.example.com:51820",
        allowed_ips="0.0.0.0/0",
        persistent_keepalive=25,
    )

    return ClientRead.model_validate(client)
