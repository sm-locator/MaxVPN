"""add private_key to wireguard_clients

Revision ID: c5c9faf426ba
Revises: 91b2632d7ac6
Create Date: 2026-07-22 12:52:53.444593

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5c9faf426ba"
down_revision: Union[str, Sequence[str], None] = "91b2632d7ac6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "wireguard_clients",
        sa.Column("private_key", sa.String(length=44), nullable=False),
    )
    op.create_unique_constraint(
        None,
        "wireguard_clients",
        ["private_key"],
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    op.drop_constraint(
        None,
        "wireguard_clients",
        type_="unique",
    )
    op.drop_column(
        "wireguard_clients",
        "private_key",
    )
    # ### end Alembic commands ###
