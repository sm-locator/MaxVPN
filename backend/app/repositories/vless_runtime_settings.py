from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.vless_runtime_settings import VlessRuntimeSettings
from app.repositories.base import BaseRepository


class VlessRuntimeSettingsRepository(BaseRepository[VlessRuntimeSettings]):
    def __init__(self, db: Session):
        super().__init__(VlessRuntimeSettings, db)

    def get_by_user(self, user_id: int) -> VlessRuntimeSettings | None:
        statement = select(VlessRuntimeSettings).where(
            VlessRuntimeSettings.user_id == user_id,
        )
        return self.db.scalar(statement)

    def get_or_create_for_user(self, user_id: int) -> VlessRuntimeSettings:
        settings = self.get_by_user(user_id)
        if settings is not None:
            return settings
        return self.create(VlessRuntimeSettings(user_id=user_id))

    def update(self, settings: VlessRuntimeSettings) -> VlessRuntimeSettings:
        return super().update(settings)
