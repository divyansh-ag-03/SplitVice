"""initial

Revision ID: 47337a1eb424
Revises:
Create Date: 2025-05-11 00:00:00.000000+00:00

Creates all MVP tables:
  users, refresh_tokens, groups, group_members,
  expenses, expense_splits, settlements

Design notes:
- group_members uses a composite PK (group_id, user_id) — no surrogate id needed.
- expense_splits uses a composite PK (expense_id, user_id) — enforces one split
  per user per expense at the DB level.
- All money columns are Numeric(19, 4) — never float.
- Soft-delete pattern: is_deleted + deleted_at on groups, expenses, settlements.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "47337a1eb424"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    # Unique index doubles as the fast lookup index for login (WHERE email = ?)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── refresh_tokens ────────────────────────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_refresh_tokens_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    # Supports: DELETE WHERE user_id = ? AND token_hash = ? (logout)
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    # ── groups ────────────────────────────────────────────────────────────────
    op.create_table(
        "groups",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_groups"),
    )

    # ── group_members ─────────────────────────────────────────────────────────
    # Composite PK (group_id, user_id) — no surrogate id needed.
    # The PK itself enforces the uniqueness constraint.
    op.create_table(
        "group_members",
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name="fk_group_members_group_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_group_members_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("group_id", "user_id", name="pk_group_members"),
    )
    # PK index covers (group_id, user_id) lookups.
    # A separate index on user_id supports: SELECT * FROM group_members WHERE user_id = ?
    op.create_index("ix_group_members_user_id", "group_members", ["user_id"])

    # ── expenses ──────────────────────────────────────────────────────────────
    op.create_table(
        "expenses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column("payer_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("split_strategy", sa.String(20), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("amount > 0", name="ck_expense_positive_amount"),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name="fk_expenses_group_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["payer_id"],
            ["users.id"],
            name="fk_expenses_payer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_expenses_created_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_expenses"),
    )
    # Supports: WHERE group_id = ? AND is_deleted = false (list expenses in group)
    op.create_index("ix_expenses_group_id", "expenses", ["group_id"])
    # Supports: balance queries and payer-filter (WHERE payer_id = ?)
    op.create_index("ix_expenses_payer_id", "expenses", ["payer_id"])

    # ── expense_splits ────────────────────────────────────────────────────────
    # Composite PK (expense_id, user_id) — enforces one split per user per
    # expense at the DB level. No surrogate id needed.
    op.create_table(
        "expense_splits",
        sa.Column("expense_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("percentage", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.CheckConstraint("amount >= 0", name="ck_split_non_negative"),
        sa.ForeignKeyConstraint(
            ["expense_id"],
            ["expenses.id"],
            name="fk_expense_splits_expense_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_expense_splits_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("expense_id", "user_id", name="pk_expense_splits"),
    )
    # PK index covers (expense_id, user_id) lookups.
    # A separate index on user_id supports balance computation:
    # SUM(amount) WHERE user_id = ? (joined with non-deleted expenses)
    op.create_index("ix_expense_splits_user_id", "expense_splits", ["user_id"])

    # ── settlements ───────────────────────────────────────────────────────────
    op.create_table(
        "settlements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column("payer_id", sa.UUID(), nullable=False),
        sa.Column("payee_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("settlement_date", sa.Date(), nullable=False),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("amount > 0", name="ck_settlement_positive_amount"),
        sa.CheckConstraint(
            "payer_id != payee_id", name="ck_settlement_different_users"
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name="fk_settlements_group_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["payer_id"],
            ["users.id"],
            name="fk_settlements_payer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["payee_id"],
            ["users.id"],
            name="fk_settlements_payee_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_settlements"),
    )
    # Supports: WHERE group_id = ? AND is_deleted = false (list settlements)
    op.create_index("ix_settlements_group_id", "settlements", ["group_id"])
    # Supports: balance computation SUM(amount) WHERE payer_id = ?
    op.create_index("ix_settlements_payer_id", "settlements", ["payer_id"])
    # Supports: balance computation SUM(amount) WHERE payee_id = ?
    op.create_index("ix_settlements_payee_id", "settlements", ["payee_id"])


def downgrade() -> None:
    # Drop in reverse dependency order (children before parents)
    op.drop_table("settlements")
    op.drop_table("expense_splits")
    op.drop_table("expenses")
    op.drop_table("group_members")
    op.drop_table("groups")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
