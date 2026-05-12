from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Expense(Base, TimestampMixin):
    """
    A monetary transaction paid by one user on behalf of a group.

    split_strategy records which algorithm was used to divide the cost:
    "equal", "exact", or "percentage". Stored for auditability.

    Soft-deleted via is_deleted + deleted_at. Hard DELETE is never used so
    that balance recalculations can always reconstruct history.

    DB constraint: amount > 0 (also validated at the service layer).

    Relationships:
    - splits: one-to-many to ExpenseSplit. cascade="all, delete-orphan" means
      when splits are replaced during an edit (delete old, insert new),
      SQLAlchemy handles the cleanup automatically.
    - payer: many-to-one to User. Loaded explicitly with selectinload() when
      rendering expense lists that need the payer's name.

    Note: created_by is stored as a plain FK column (not a relationship) because
    it is only used for authorization checks (compare UUID, never load the User).
    """

    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expense_positive_amount"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,  # list expenses in a group: WHERE group_id = ? AND is_deleted = false
    )
    payer_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,  # balance queries and payer-filter: WHERE payer_id = ?
    )
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        # no relationship — only used for UUID comparison in auth checks
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    # Numeric(19, 4): up to 999,999,999,999,999.9999 — sufficient for any
    # real-world expense. 4 decimal places handle percentage splits that
    # produce sub-cent amounts before rounding.
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=19, scale=4), nullable=False
    )
    split_strategy: Mapped[str] = mapped_column(
        String(20), nullable=False
        # "equal" | "exact" | "percentage"
    )
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    splits: Mapped[list["ExpenseSplit"]] = relationship(
        "ExpenseSplit",
        back_populates="expense",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    payer: Mapped["User"] = relationship(  # noqa: F821
        "User",
        foreign_keys=[payer_id],
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Expense id={self.id} amount={self.amount} group={self.group_id}>"


class ExpenseSplit(Base):
    """
    The portion of an Expense owed by a specific user.

    Uses a composite primary key (expense_id, user_id) — this is the natural
    key and also enforces that a user can only appear once per expense at the
    DB level, without needing a separate surrogate id column.

    The sum of all split amounts for an expense must equal the expense total
    (enforced at the service layer; the DB only ensures amount >= 0).

    percentage is nullable: only populated when split_strategy="percentage",
    stored for display purposes (e.g. "you owe 33.33%").

    Cascade: rows are deleted automatically when the parent Expense is deleted
    or when splits are replaced during an expense edit.
    """

    __tablename__ = "expense_splits"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_split_non_negative"),
    )

    expense_id: Mapped[UUID] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        primary_key=True,
        index=True,  # balance computation: SUM(amount) WHERE user_id = ?
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=19, scale=4), nullable=False
    )
    # Numeric(7, 4): stores values like 33.3333 — up to 999.9999%
    percentage: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=7, scale=4), nullable=True
    )

    # Relationships
    expense: Mapped["Expense"] = relationship(
        "Expense",
        back_populates="splits",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<ExpenseSplit expense={self.expense_id} user={self.user_id} amount={self.amount}>"
