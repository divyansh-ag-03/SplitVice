"""add settlement creator_id

Revision ID: f8a86943b1b4
Revises: 47337a1eb424
Create Date: 2025-05-11 00:01:00.000000+00:00

Adds creator_id to the settlements table so we can enforce
"only the creator can delete this settlement".
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f8a86943b1b4"
down_revision: Union[str, None] = "47337a1eb424"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add creator_id as nullable first so existing rows (if any) don't fail,
    # then set a sensible default (payer_id) for any pre-existing rows,
    # then make it non-nullable.
    op.add_column(
        "settlements",
        sa.Column("creator_id", sa.UUID(), nullable=True),
    )
    # Back-fill: treat payer as creator for any existing rows
    op.execute("UPDATE settlements SET creator_id = payer_id WHERE creator_id IS NULL")
    op.alter_column("settlements", "creator_id", nullable=False)
    op.create_foreign_key(
        "fk_settlements_creator_id",
        "settlements",
        "users",
        ["creator_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # Add optional description column
    op.add_column(
        "settlements",
        sa.Column("description", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("settlements", "description")
    op.drop_constraint("fk_settlements_creator_id", "settlements", type_="foreignkey")
    op.drop_column("settlements", "creator_id")
