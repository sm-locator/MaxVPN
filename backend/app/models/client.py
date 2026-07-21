from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Client(BaseModel):
    __tablename__ = "clients"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    server_id: Mapped[int] = mapped_column(
        ForeignKey("servers.id"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    private_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    public_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    preshared_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    address: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    dns: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    allowed_ips: Mapped[str] = mapped_column(
        String(255),
        default="0.0.0.0/0",
        nullable=False,
    )

    persistent_keepalive: Mapped[int] = mapped_column(
        Integer,
        default=25,
        nullable=False,
    )

    user = relationship("User", back_populates="clients")

    server = relationship("Server", back_populates="clients")
