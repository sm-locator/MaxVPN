from sqlalchemy.orm import Session

from app.models.server import Server
from app.repositories.base import BaseRepository


class ServerRepository(BaseRepository[Server]):
    def __init__(self, db: Session):
        super().__init__(Server, db)

    def get_by_name(self, name: str) -> Server | None:
        return self.db.query(Server).filter(Server.name == name).first()
