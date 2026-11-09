from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class SmartRoutingDnsDomainStateRecord(BaseModel):
    """Last successfully observed A/AAAA answers for one DIRECT domain."""

    __tablename__ = "smart_routing_dns_domain_states"
    __table_args__ = (
        UniqueConstraint("domain", name="uq_smart_routing_dns_domain_states_domain"),
    )

    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    ipv4_addresses: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    ipv6_addresses: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )


class SmartRoutingDnsIpSetOutboxRecord(BaseModel):
    """Durable desired state for one address in a DNS-derived ipset."""

    __tablename__ = "smart_routing_dns_ipset_outbox"
    __table_args__ = (
        UniqueConstraint(
            "address_family",
            "address",
            name="uq_smart_routing_dns_ipset_outbox_family_address",
        ),
        CheckConstraint(
            "address_family IN ('ipv4', 'ipv6')",
            name="ck_smart_routing_dns_ipset_outbox_address_family",
        ),
    )

    address_family: Mapped[str] = mapped_column(String(4), nullable=False)
    address: Mapped[str] = mapped_column(String(45), nullable=False)
    desired_present: Mapped[bool] = mapped_column(Boolean, nullable=False)
