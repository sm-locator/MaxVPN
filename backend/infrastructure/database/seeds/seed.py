from backend.infrastructure.database.mappers.server_mapper import ServerMapper
from backend.infrastructure.database.models.server_model import ServerModel
from backend.infrastructure.database.seeds.fixtures import SERVERS
from sqlalchemy import select
from sqlalchemy.orm import Session


def seed_database(session: Session) -> None:
    """
    Populate the database with initial data.

    Safe to call multiple times.
    """

    existing = session.scalar(select(ServerModel.id).limit(1))

    if existing is not None:
        return

    session.add_all([ServerMapper.to_model(server) for server in SERVERS])

    session.commit()
