from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.server import Server
from app.repositories.server import ServerRepository
from app.schemas.server import (
    ServerCreate,
    ServerUpdate,
)


class ServerService:
    def __init__(self, db: Session):
        self.repository = ServerRepository(db)

    def create(self, data: ServerCreate) -> Server:
        if self.repository.get_by_name(data.name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Server already exists",
            )

        server = Server(**data.model_dump())

        return self.repository.create(server)

    def get(self, server_id: int) -> Server | None:
        return self.repository.get(server_id)

    def get_or_404(self, server_id: int) -> Server:
        server = self.repository.get(server_id)

        if server is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Server not found",
            )

        return server

    def get_all(self) -> list[Server]:
        return self.repository.get_all()

    def update(
        self,
        server: Server,
        data: ServerUpdate,
    ) -> Server:
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(server, key, value)

        return self.repository.update(server)

    def delete(self, server: Server) -> None:
        self.repository.delete(server)
