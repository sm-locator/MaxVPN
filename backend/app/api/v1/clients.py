from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from fastapi.responses import PlainTextResponse

from app.api.dependencies import (
    get_export_facade,
    get_wireguard_manager,
    get_wireguard_server_settings,
)
from app.auth.dependencies import require_role
from app.exporters.export_facade import ExportFacade
from app.models.roles import UserRole
from app.schemas.wireguard_client import (
    ClientCreate,
    ClientListItem,
    ClientRead,
    ClientUpdate,
)
from app.vpn.exceptions import ClientNotFoundError
from app.vpn.wireguard.manager import WireGuardManager
from app.vpn.wireguard.server_settings import WireGuardServerSettings

router = APIRouter(
    prefix="/clients",
    tags=["Clients"],
    # Legacy peers are global and have no owner to scope access to.
    dependencies=[Depends(require_role(UserRole.ADMIN))],
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


@router.get(
    "",
    response_model=list[ClientListItem],
)
def list_clients(
    manager: WireGuardManager = Depends(get_wireguard_manager),
) -> list[ClientRead]:
    return [ClientListItem.model_validate(client) for client in manager.list_clients()]


@router.get(
    "/{client_name}",
    response_model=ClientListItem,
)
def get_client(
    client_name: str,
    manager: WireGuardManager = Depends(get_wireguard_manager),
) -> ClientListItem:
    try:
        client = manager.get_client(client_name)
    except ClientNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return ClientListItem.model_validate(client)


@router.put(
    "/{client_name}",
    response_model=ClientListItem,
)
def update_client(
    client_name: str,
    data: ClientUpdate,
    manager: WireGuardManager = Depends(get_wireguard_manager),
) -> ClientListItem:
    client = manager.update_client(
        client_name=client_name,
        name=data.name,
        description=data.description,
        enabled=data.enabled,
    )

    return ClientListItem.model_validate(client)


@router.delete(
    "/{client_name}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_client(
    client_name: str,
    manager: WireGuardManager = Depends(get_wireguard_manager),
) -> Response:
    try:
        manager.delete_client(client_name)
    except ClientNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{client_name}/config",
    response_class=PlainTextResponse,
)
def get_client_config(
    client_name: str,
    manager: WireGuardManager = Depends(get_wireguard_manager),
    server_settings: WireGuardServerSettings = Depends(
        get_wireguard_server_settings,
    ),
    exporter: ExportFacade = Depends(
        get_export_facade,
    ),
) -> PlainTextResponse:
    config = manager.get_client_config(
        client_name=client_name,
        server=server_settings,
    )

    return exporter.export_config(
        config=config,
        filename=client_name,
    )


@router.get(
    "/{client_name}/qr",
)
def get_client_qr(
    client_name: str,
    manager: WireGuardManager = Depends(
        get_wireguard_manager,
    ),
    server_settings: WireGuardServerSettings = Depends(
        get_wireguard_server_settings,
    ),
    exporter: ExportFacade = Depends(
        get_export_facade,
    ),
) -> Response:
    config = manager.get_client_config(
        client_name=client_name,
        server=server_settings,
    )

    png = exporter.export_qr(config)

    return Response(
        content=png,
        media_type="image/png",
    )


@router.post(
    "/{client_name}/disable",
    status_code=status.HTTP_204_NO_CONTENT,
)
def disable_client(
    client_name: str,
    manager: WireGuardManager = Depends(get_wireguard_manager),
) -> Response:
    manager.disable_client(client_name)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{client_name}/enable", status_code=status.HTTP_204_NO_CONTENT)
def enable_client(
    client_name: str,
    manager: WireGuardManager = Depends(get_wireguard_manager),
) -> None:
    manager.enable_client(client_name)
