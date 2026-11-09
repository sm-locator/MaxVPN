from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.vpn_profile import VpnProfile
from app.repositories.base import BaseRepository


class VpnProfileRepository(BaseRepository[VpnProfile]):
    def __init__(self, db: Session):
        super().__init__(VpnProfile, db)

    def get_by_user(self, user_id: int) -> VpnProfile | None:
        stmt = select(VpnProfile).where(
            VpnProfile.user_id == user_id,
        )
        return self.db.scalar(stmt)

    def create_for_user(
        self,
        user_id: int,
        name: str,
        encrypted_provider_config: str,
        enabled: bool = True,
    ) -> VpnProfile:
        profile = VpnProfile(
            user_id=user_id,
            name=name,
            encrypted_provider_config=encrypted_provider_config,
            enabled=enabled,
        )

        return self.create(profile)
