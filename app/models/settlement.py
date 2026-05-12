from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Settlement(Base):
    """
    A payment made by one user to another to reduce or eliminate a debt.

    Settlements are a direct transfer between two users within a group context.
    group_id is stored so balance queries can scope settlements to a group.

    Immutable except for soft-deletion: once created, only is_deleted and
    deleted_at may change. Soft-deleting a settlement reverses its effect on
    balances (handled at the service layer).

    Settlement intentionally does NOT use TimestampMixin because there is no
    meaningful updated_at — the record is either active or soft-deleted.
    Only created_at is needed.

    DB constraints:
    - amount > 0: a settlement must transfer a positive amount.
    - payer_id != payee_id: you cannot settle a debt with yourself.
      Note: SQLite (used in tests) does not enforce CHECK constraints by
      default. The service layer validates this before any DB write.

    FK behaviour: all three FKs use RESTRICT — a user or group cannot be
    deleted while settlement records reference them.

    No ORM relationships are defined here. Balance queries use raw SQL
    aggregates (SUM with GROUP BY) — loading User objects via relationship
    traversal would cause N+1 queries and is never needed.
    """

    __tablename__ = "settlements"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_settlement_positive_amount"),
        CheckConstraint("payer_id != payee_id", name="ck_settlement_different_users"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    payer_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    payee_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # The user who recorded this settlement (may differ from payer).
    # Used for authorization: only the creator can soft-delete.
    creator_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=19, scale=4), nullable=False
    )
    settlement_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Settlement id={self.id} "
            f"payer={self.payer_id} payee={self.payee_id} "
            f"amount={self.amount}>"
        )
