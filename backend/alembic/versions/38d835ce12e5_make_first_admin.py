"""make first admin

Revision ID: 38d835ce12e5
Revises: 86635d8d45b2
Create Date: 2026-07-05 15:57:46.911834

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "38d835ce12e5"
down_revision: Union[str, Sequence[str], None] = "86635d8d45b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE users
        SET role = 'admin'
        WHERE email = 'admin@gmail.com';
        """)


def downgrade() -> None:
    op.execute("""
        UPDATE users
        SET role = 'user'
        WHERE email = 'admin@gmail.com';
        """)
