"""create vpn profiles

Revision ID: 83feff1937ba
Revises: 1f98f0742750
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "83feff1937ba"
down_revision: Union[str, Sequence[str], None] = "1f98f0742750"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create VPN profiles table."""
    op.create_table(
        "vpn_profiles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "encrypted_provider_config",
            sa.String(),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_vpn_profiles_user_id",
        "vpn_profiles",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    """Drop VPN profiles table."""
    op.drop_index(
        "ix_vpn_profiles_user_id",
        table_name="vpn_profiles",
    )
    op.drop_table("vpn_profiles")
