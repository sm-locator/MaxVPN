from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.roles import UserRole


class User(BaseModel):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[UserRole] = mapped_column(
        String(30),
        default=UserRole.USER,
        nullable=False,
    )

    clients = relationship(
        "Client",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    smart_routing_rules = relationship(
        "SmartRoutingRule",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    vpn_profile = relationship(
        "VpnProfile",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
