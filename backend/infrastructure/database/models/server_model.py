from __future__ import annotations

from backend.infrastructure.database.base import Base
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class ServerModel(Base):
    """
    Database representation of a VPN server.
    """

    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    country: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
    )

    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    endpoint: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    public_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    online: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    maintenance: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    load: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    latency: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    max_load: Mapped[int] = mapped_column(
        Integer,
        default=80,
        nullable=False,
    )

    max_devices: Mapped[int] = mapped_column(
        Integer,
        default=1000,
        nullable=False,
    )
