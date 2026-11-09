"""add persistent VLESS profile availability history

Revision ID: d46ac7901c2b
Revises: b62e37a96c41
Create Date: 2026-10-20
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d46ac7901c2b"
down_revision: Union[str, Sequence[str], None] = "b62e37a96c41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vless_profiles", sa.Column("last_delay_ms", sa.Integer(), nullable=True)
    )
    op.add_column(
        "vless_profiles",
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "vless_profiles",
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "vless_profiles",
        sa.Column("first_failed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "vless_profiles",
        sa.Column("last_outage_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "vless_profiles",
        sa.Column("last_recovered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "vless_profiles",
        sa.Column("last_outage_duration_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "vless_profiles",
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    for name in (
        "consecutive_failures",
        "last_outage_duration_seconds",
        "last_recovered_at",
        "last_outage_started_at",
        "first_failed_at",
        "last_success_at",
        "last_checked_at",
        "last_delay_ms",
    ):
        op.drop_column("vless_profiles", name)
