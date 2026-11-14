from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class SmartRoutingDependencyGroup(BaseModel):
    __tablename__ = "smart_routing_dependency_groups"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    site_domain: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    user = relationship("User")

    items = relationship(
        "SmartRoutingDependencyGroupItem",
        back_populates="group",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "site_domain",
            name="uq_smart_routing_dependency_group_user_domain",
        ),
    )


class SmartRoutingDependencyGroupItem(BaseModel):
    __tablename__ = "smart_routing_dependency_group_items"

    group_id: Mapped[int] = mapped_column(
        ForeignKey(
            "smart_routing_dependency_groups.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    rule_id: Mapped[int] = mapped_column(
        ForeignKey(
            "smart_routing_rules.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    group = relationship(
        "SmartRoutingDependencyGroup",
        back_populates="items",
    )

    rule = relationship("SmartRoutingRule")

    __table_args__ = (
        UniqueConstraint(
            "group_id",
            "rule_id",
            name="uq_smart_routing_dependency_group_item",
        ),
    )
