from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class VlessRuntimeSettings(BaseModel):
    """Per-user tuning for sing-box URLTest server selection."""

    __tablename__ = "vless_runtime_settings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    urltest_interval: Mapped[str] = mapped_column(
        String(8), nullable=False, default="3m"
    )
    urltest_tolerance_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=50
    )
