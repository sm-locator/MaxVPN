from backend.infrastructure.database.models.client_model import ClientModel
from backend.models.client import Client


class ClientMapper:
    """
    Maps between SQLAlchemy models and domain models.
    """

    @staticmethod
    def to_domain(model: ClientModel) -> Client:
        return Client(
            id=model.id,
            name=model.name,
            server_id=model.server_id,
            private_key=model.private_key,
            public_key=model.public_key,
            address=model.address,
            description=model.description,
            enabled=model.enabled,
        )

    @staticmethod
    def to_model(client: Client) -> ClientModel:
        return ClientModel(
            id=client.id,
            name=client.name,
            server_id=client.server_id,
            private_key=client.private_key,
            public_key=client.public_key,
            address=client.address,
            description=client.description,
            enabled=client.enabled,
        )
