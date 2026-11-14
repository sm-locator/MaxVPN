from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.vless_profile import VlessProfile
from app.repositories.base import BaseRepository


class VlessProfileRepository(BaseRepository[VlessProfile]):
    def __init__(self, db: Session):
        super().__init__(VlessProfile, db)

    def list_by_user(self, user_id: int) -> list[VlessProfile]:
        statement = (
            select(VlessProfile)
            .where(VlessProfile.user_id == user_id)
            .order_by(VlessProfile.id.asc())
        )
        return list(self.db.scalars(statement).all())

    def get_by_user(self, user_id: int) -> VlessProfile | None:
        """Return an enabled profile first for compatibility with the old API."""
        statement = (
            select(VlessProfile)
            .where(VlessProfile.user_id == user_id)
            .order_by(VlessProfile.enabled.desc(), VlessProfile.id.asc())
            .limit(1)
        )
        return self.db.scalar(statement)

    def get_by_id_for_user(
        self,
        user_id: int,
        profile_id: int,
    ) -> VlessProfile | None:
        statement = select(VlessProfile).where(
            VlessProfile.user_id == user_id,
            VlessProfile.id == profile_id,
        )
        return self.db.scalar(statement)

    def count_by_user(self, user_id: int) -> int:
        statement = (
            select(func.count())
            .select_from(VlessProfile)
            .where(
                VlessProfile.user_id == user_id,
            )
        )
        return int(self.db.scalar(statement) or 0)

    def create_for_user(
        self,
        user_id: int,
        name: str,
        encrypted_config: str,
        enabled: bool = True,
    ) -> VlessProfile:
        profile = VlessProfile(
            user_id=user_id,
            name=name,
            encrypted_config=encrypted_config,
            enabled=enabled,
        )
        return self.create(profile)

    def update(self, profile: VlessProfile) -> VlessProfile:
        return super().update(profile)

    def update_many(self, profiles: list[VlessProfile]) -> list[VlessProfile]:
        """Persist multiple profile monitoring updates in one transaction."""
        if not profiles:
            return []
        for profile in profiles:
            self.db.add(profile)
        self.db.commit()
        for profile in profiles:
            self.db.refresh(profile)
        return profiles

    def delete_for_user(self, user_id: int, profile_id: int) -> bool:
        profile = self.get_by_id_for_user(user_id, profile_id)
        if profile is None:
            return False
        self.db.delete(profile)
        self.db.commit()
        return True
