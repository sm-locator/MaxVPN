from backend.infrastructure.database.mappers.client_mapper import ClientMapper
from backend.infrastructure.database.models.client_model import ClientModel
from backend.models.client import Client
from backend.ports.client_repository import ClientRepository
from sqlalchemy import select
from sqlalchemy.orm import Session


class SqlAlchemyClientRepository(ClientRepository):
    """
    SQLAlchemy implementation of the ClientRepository port.
    """

    def __init__(self, session: Session):
        self._session = session

    def get_used_addresses(self) -> set[str]:
        addresses = self._session.scalars(select(ClientModel.address)).all()

        return set(addresses)

    def add(self, client: Client) -> None:
        model = ClientMapper.to_model(client)

        self._session.add(model)
        self._session.flush()

        client.id = model.id

    def get_by_name(self, name: str) -> Client | None:
        model = self._session.scalar(
            select(ClientModel).where(
                ClientModel.name == name,
            )
        )

        if model is None:
            return None

        return ClientMapper.to_domain(model)

    def delete(self, client: Client) -> None:
        model = self._session.scalar(
            select(ClientModel).where(
                ClientModel.id == client.id,
            )
        )

        if model is not None:
            self._session.delete(model)

    def get_by_server_id(self, server_id: int) -> list[Client]:
        models = self._session.scalars(
            select(ClientModel).where(
                ClientModel.server_id == server_id,
                ClientModel.enabled.is_(True),
            )
        ).all()

        return [ClientMapper.to_domain(model) for model in models]
