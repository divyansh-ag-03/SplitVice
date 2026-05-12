"""
Balance aggregate queries.

All functions return raw Decimal totals keyed by user_id.
No business logic, no debt simplification, no authorization.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense, ExpenseSplit
from app.models.group import GroupMember
from app.models.settlement import Settlement
from app.models.user import User

# Canonical zero — used as a default when a user has no rows in a table
ZERO = Decimal("0.0000")


async def get_member_user_ids(db: AsyncSession, group_id: UUID) -> list[UUID]:
    """Return all user_ids currently in the group."""
    result = await db.execute(
        select(GroupMember.user_id).where(GroupMember.group_id == group_id)
    )
    return list(result.scalars().all())


async def get_user_names(
    db: AsyncSession, user_ids: list[UUID]
) -> dict[UUID, str]:
    """Return {user_id: name} for the given ids."""
    if not user_ids:
        return {}
    result = await db.execute(
        select(User.id, User.name).where(User.id.in_(user_ids))
    )
    return {row.id: row.name for row in result.all()}


async def get_paid_totals(
    db: AsyncSession, group_id: UUID
) -> dict[UUID, Decimal]:
    """
    For each user: sum of expense amounts where they are the payer,
    excluding soft-deleted expenses.
    Returns {user_id: total_paid}.
    """
    result = await db.execute(
        select(Expense.payer_id, func.sum(Expense.amount).label("total"))
        .where(
            Expense.group_id == group_id,
            Expense.is_deleted.is_(False),
        )
        .group_by(Expense.payer_id)
    )
    return {row.payer_id: Decimal(str(row.total)) for row in result.all()}


async def get_owed_totals(
    db: AsyncSession, group_id: UUID
) -> dict[UUID, Decimal]:
    """
    For each user: sum of split amounts assigned to them,
    excluding splits from soft-deleted expenses.
    Returns {user_id: total_owed}.
    """
    result = await db.execute(
        select(ExpenseSplit.user_id, func.sum(ExpenseSplit.amount).label("total"))
        .join(Expense, Expense.id == ExpenseSplit.expense_id)
        .where(
            Expense.group_id == group_id,
            Expense.is_deleted.is_(False),
        )
        .group_by(ExpenseSplit.user_id)
    )
    return {row.user_id: Decimal(str(row.total)) for row in result.all()}


async def get_settlement_paid_totals(
    db: AsyncSession, group_id: UUID
) -> dict[UUID, Decimal]:
    """
    For each user: sum of settlements where they are the payer,
    excluding soft-deleted settlements.
    Returns {user_id: total_paid_in_settlements}.
    """
    result = await db.execute(
        select(Settlement.payer_id, func.sum(Settlement.amount).label("total"))
        .where(
            Settlement.group_id == group_id,
            Settlement.is_deleted.is_(False),
        )
        .group_by(Settlement.payer_id)
    )
    return {row.payer_id: Decimal(str(row.total)) for row in result.all()}


async def get_settlement_received_totals(
    db: AsyncSession, group_id: UUID
) -> dict[UUID, Decimal]:
    """
    For each user: sum of settlements where they are the payee,
    excluding soft-deleted settlements.
    Returns {user_id: total_received_in_settlements}.
    """
    result = await db.execute(
        select(Settlement.payee_id, func.sum(Settlement.amount).label("total"))
        .where(
            Settlement.group_id == group_id,
            Settlement.is_deleted.is_(False),
        )
        .group_by(Settlement.payee_id)
    )
    return {row.payee_id: Decimal(str(row.total)) for row in result.all()}
