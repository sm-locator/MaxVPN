from typing import Generic, TypeVar

from sqlalchemy.orm import Session

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: type[ModelType], db: Session):
        self.model = model
        self.db = db

    def create(self, obj: ModelType) -> ModelType:
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def get(self, obj_id: int) -> ModelType | None:
        return self.db.get(self.model, obj_id)

    def get_all(self) -> list[ModelType]:
        return self.db.query(self.model).all()

    def delete(self, obj: ModelType) -> None:
        self.db.delete(obj)
        self.db.commit()

    def update(self, obj: ModelType) -> ModelType:
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def exists(self, obj_id: int) -> bool:
        return self.get(obj_id) is not None
