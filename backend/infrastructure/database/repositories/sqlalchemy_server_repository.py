from backend.infrastructure.database.mappers.server_mapper import ServerMapper
from backend.infrastructure.database.models.server_model import ServerModel
from backend.models.server import Server
from backend.ports.server_repository import ServerRepository
from sqlalchemy import select
from sqlalchemy.orm import Session


class SqlAlchemyServerRepository(ServerRepository):
    """
    SQLAlchemy implementation of the ServerRepository port.
    """

    def __init__(self, session: Session):
        self._session = session

    def get_all(self) -> list[Server]:
        models = self._session.scalars(select(ServerModel)).all()

        return [ServerMapper.to_domain(model) for model in models]

    def get_available(self) -> list[Server]:
        models = self._session.scalars(
            select(ServerModel).where(
                ServerModel.online.is_(True),
                ServerModel.maintenance.is_(False),
            )
        ).all()

        return [ServerMapper.to_domain(model) for model in models]

    def update(self, server: Server) -> None:
        model = self._session.scalar(
            select(ServerModel).where(
                ServerModel.id == server.id,
            )
        )

        if model is None:
            raise ValueError(f"Server with id {server.id} does not exist.")

        model.name = server.name
        model.country = server.country
        model.city = server.city
        model.endpoint = server.endpoint
        model.public_key = server.public_key
        model.online = server.online
        model.maintenance = server.maintenance
        model.load = server.load
        model.latency = server.latency
        model.max_load = server.max_load
        model.max_devices = server.max_devices

    def get_by_id(self, server_id: int) -> Server | None:
        model = self._session.scalar(
            select(ServerModel).where(
                ServerModel.id == server_id,
            )
        )

        if model is None:
            return None

        return ServerMapper.to_domain(model)
