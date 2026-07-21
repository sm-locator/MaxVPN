from sqlalchemy import Boolean, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import ServerStatus, VPNProtocol


class Server(BaseModel):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )

    country: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    hostname: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    public_ip: Mapped[str] = mapped_column(
        String(45),
        nullable=False,
    )

    wireguard_port: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    vpn_protocol: Mapped[VPNProtocol] = mapped_column(
        SQLEnum(VPNProtocol),
        default=VPNProtocol.WIREGUARD,
        nullable=False,
    )

    status: Mapped[ServerStatus] = mapped_column(
        SQLEnum(ServerStatus),
        default=ServerStatus.ONLINE,
        nullable=False,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    display_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    clients = relationship(
        "Client",
        back_populates="server",
        cascade="all, delete-orphan",
    )
