"""add smart routing dependency groups

Revision ID: 0ffda25442bd
Revises: 83feff1937ba
Create Date: 2026-09-16
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0ffda25442bd"
down_revision: Union[str, Sequence[str], None] = "83feff1937ba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "smart_routing_dependency_groups",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("site_domain", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "site_domain",
            name="uq_smart_routing_dependency_group_user_domain",
        ),
    )

    op.create_index(
        "ix_smart_routing_dependency_groups_user_id",
        "smart_routing_dependency_groups",
        ["user_id"],
    )

    op.create_table(
        "smart_routing_dependency_group_items",
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["smart_routing_dependency_groups.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["smart_routing_rules.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "group_id",
            "rule_id",
            name="uq_smart_routing_dependency_group_item",
        ),
    )

    op.create_index(
        "ix_smart_routing_dependency_group_items_group_id",
        "smart_routing_dependency_group_items",
        ["group_id"],
    )

    op.create_index(
        "ix_smart_routing_dependency_group_items_rule_id",
        "smart_routing_dependency_group_items",
        ["rule_id"],
    )


def downgrade() -> None:
    op.drop_table("smart_routing_dependency_group_items")
    op.drop_index(
        "ix_smart_routing_dependency_groups_user_id",
        table_name="smart_routing_dependency_groups",
    )
    op.drop_table("smart_routing_dependency_groups")
