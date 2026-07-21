"""create wireguard clients table

Revision ID: 91b2632d7ac6
Revises: c4b294c90ca2
Create Date: 2026-07-19 19:55:22.982458

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "91b2632d7ac6"
down_revision: Union[str, Sequence[str], None] = "c4b294c90ca2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "wireguard_clients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("public_key", sa.String(length=44), nullable=False),
        sa.Column("ip_address", postgresql.INET(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ip_address"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("public_key"),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_table("wireguard_clients")
