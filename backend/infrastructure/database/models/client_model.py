from __future__ import annotations

from backend.infrastructure.database.base import Base
from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class ClientModel(Base):
    """
    Database representation of a VPN client.
    """

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )

    server_id: Mapped[int] = mapped_column(
        ForeignKey("servers.id"),
        nullable=False,
    )

    private_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    public_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
    )

    address: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
    )

    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
