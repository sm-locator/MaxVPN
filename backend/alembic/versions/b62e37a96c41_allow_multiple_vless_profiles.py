"""Allow up to 50 VLESS profiles per user.

Revision ID: b62e37a96c41
Revises: 2a6f19c4b8d1
Create Date: 2026-10-16
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b62e37a96c41"
down_revision: Union[str, Sequence[str], None] = "2a6f19c4b8d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Preserve the existing unique profile row while removing the per-user
    # uniqueness constraint. Keep a regular index for user-scoped lookups.
    op.drop_index("ix_vless_profiles_user_id", table_name="vless_profiles")
    op.create_index(
        "ix_vless_profiles_user_id",
        "vless_profiles",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "vless_runtime_settings",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "urltest_interval", sa.String(length=8), server_default="3m", nullable=False
        ),
        sa.Column(
            "urltest_tolerance_ms", sa.Integer(), server_default="50", nullable=False
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_vless_runtime_settings_user_id",
        "vless_runtime_settings",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    # Check first: refusing a downgrade must not drop the settings table.
    connection = op.get_bind()
    duplicates = connection.execute(
        sa.text(
            "SELECT user_id FROM vless_profiles GROUP BY user_id "
            "HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicates is not None:
        raise RuntimeError(
            "Cannot downgrade: users have multiple VLESS profiles. "
            "Delete extra profiles before retrying."
        )
    op.drop_index(
        "ix_vless_runtime_settings_user_id", table_name="vless_runtime_settings"
    )
    op.drop_table("vless_runtime_settings")
    op.drop_index("ix_vless_profiles_user_id", table_name="vless_profiles")
    op.create_index(
        "ix_vless_profiles_user_id",
        "vless_profiles",
        ["user_id"],
        unique=True,
    )
