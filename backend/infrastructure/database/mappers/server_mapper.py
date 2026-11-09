from backend.infrastructure.database.models.server_model import ServerModel
from backend.models.server import Server


class ServerMapper:
    """
    Maps between SQLAlchemy models and domain models.
    """

    @staticmethod
    def to_domain(model: ServerModel) -> Server:
        return Server(
            id=model.id,
            name=model.name,
            country=model.country,
            city=model.city,
            endpoint=model.endpoint,
            public_key=model.public_key,
            online=model.online,
            maintenance=model.maintenance,
            load=model.load,
            latency=model.latency,
            max_load=model.max_load,
            max_devices=model.max_devices,
        )

    @staticmethod
    def to_model(server: Server) -> ServerModel:
        return ServerModel(
            id=server.id,
            name=server.name,
            country=server.country,
            city=server.city,
            endpoint=server.endpoint,
            public_key=server.public_key,
            online=server.online,
            maintenance=server.maintenance,
            load=server.load,
            latency=server.latency,
            max_load=server.max_load,
            max_devices=server.max_devices,
        )
