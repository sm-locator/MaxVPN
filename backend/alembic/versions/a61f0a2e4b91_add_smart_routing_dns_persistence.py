"""add persistent smart routing DNS ownership and ipset outbox

Revision ID: a61f0a2e4b91
Revises: d46ac7901c2b
Create Date: 2026-10-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a61f0a2e4b91"
down_revision: Union[str, Sequence[str], None] = "d46ac7901c2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "smart_routing_dns_domain_states",
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column(
            "ipv4_addresses",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "ipv6_addresses",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "domain",
            name="uq_smart_routing_dns_domain_states_domain",
        ),
    )

    op.create_table(
        "smart_routing_dns_ipset_outbox",
        sa.Column("address_family", sa.String(length=4), nullable=False),
        sa.Column("address", sa.String(length=45), nullable=False),
        sa.Column("desired_present", sa.Boolean(), nullable=False),
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
        sa.CheckConstraint(
            "address_family IN ('ipv4', 'ipv6')",
            name="ck_smart_routing_dns_ipset_outbox_address_family",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "address_family",
            "address",
            name="uq_smart_routing_dns_ipset_outbox_family_address",
        ),
    )


def downgrade() -> None:
    op.drop_table("smart_routing_dns_ipset_outbox")
    op.drop_table("smart_routing_dns_domain_states")
