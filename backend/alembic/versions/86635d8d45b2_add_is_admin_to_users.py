"""add is_admin to users

Revision ID: 86635d8d45b2
Revises: 661f3123e96e
Create Date: 2026-07-05 14:37:54.336813
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "86635d8d45b2"
down_revision: Union[str, Sequence[str], None] = "661f3123e96e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "is_admin")
