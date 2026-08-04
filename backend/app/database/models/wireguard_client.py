from sqlalchemy import String
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class WireGuardClient(Base):
    __tablename__ = "wireguard_clients"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    private_key: Mapped[str] = mapped_column(
        String(44),
        unique=True,
        nullable=False,
    )

    public_key: Mapped[str] = mapped_column(
        String(44),
        unique=True,
        nullable=False,
    )

    ip_address: Mapped[str] = mapped_column(
        INET,
        unique=True,
        nullable=False,
    )
