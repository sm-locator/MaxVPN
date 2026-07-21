from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.database.dependencies import get_db
from app.models.roles import UserRole
from app.schemas.server import (
    ServerCreate,
    ServerRead,
    ServerUpdate,
)
from app.services.server import ServerService

router = APIRouter(
    prefix="/servers",
    tags=["Servers"],
)


@router.post(
    "",
    response_model=ServerRead,
    status_code=status.HTTP_201_CREATED,
)
def create_server(
    data: ServerCreate,
    db: Session = Depends(get_db),
    _: object = Depends(require_role(UserRole.ADMIN)),
):
    return ServerService(db).create(data)


@router.get(
    "",
    response_model=list[ServerRead],
)
def get_servers(
    db: Session = Depends(get_db),
    _: object = Depends(require_role(UserRole.ADMIN)),
):
    return ServerService(db).get_all()


@router.get(
    "/{server_id}",
    response_model=ServerRead,
)
def get_server(
    server_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_role(UserRole.ADMIN)),
):
    return ServerService(db).get_or_404(server_id)


@router.patch(
    "/{server_id}",
    response_model=ServerRead,
)
def update_server(
    server_id: int,
    data: ServerUpdate,
    db: Session = Depends(get_db),
    _: object = Depends(require_role(UserRole.ADMIN)),
):
    service = ServerService(db)

    server = service.get_or_404(server_id)

    return service.update(server, data)


@router.delete(
    "/{server_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_server(
    server_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_role(UserRole.ADMIN)),
):
    service = ServerService(db)

    server = service.get_or_404(server_id)

    service.delete(server)
