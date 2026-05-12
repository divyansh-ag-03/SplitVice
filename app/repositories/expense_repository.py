"""
Expense and ExpenseSplit data-access functions.

Thin DB layer — no business logic, no validation, no authorization.
All functions accept an AsyncSession and return ORM objects.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense, ExpenseSplit


async def create_expense(
    db: AsyncSession,
    *,
    group_id: UUID,
    payer_id: UUID,
    created_by: UUID,
    description: str,
    amount: Decimal,
    expense_date: date,
) -> Expense:
    expense = Expense(
        group_id=group_id,
        payer_id=payer_id,
        created_by=created_by,
        description=description,
        amount=amount,
        split_strategy="exact",  # MVP only supports exact splits
        expense_date=expense_date,
    )
    db.add(expense)
    await db.flush()  # get the id without committing
    await db.refresh(expense)
    return expense


async def create_expense_splits(
    db: AsyncSession,
    expense_id: UUID,
    splits: list[tuple[UUID, Decimal]],  # (user_id, amount)
) -> None:
    for user_id, amount in splits:
        db.add(ExpenseSplit(expense_id=expense_id, user_id=user_id, amount=amount))
    await db.flush()


async def delete_expense_splits(db: AsyncSession, expense_id: UUID) -> None:
    await db.execute(
        delete(ExpenseSplit).where(ExpenseSplit.expense_id == expense_id)
    )


async def list_expense_splits(
    db: AsyncSession, expense_id: UUID
) -> list[ExpenseSplit]:
    result = await db.execute(
        select(ExpenseSplit).where(ExpenseSplit.expense_id == expense_id)
    )
    return list(result.scalars().all())


async def get_expense_by_id(db: AsyncSession, expense_id: UUID) -> Expense | None:
    result = await db.execute(
        select(Expense).where(
            Expense.id == expense_id,
            Expense.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def list_group_expenses(
    db: AsyncSession, group_id: UUID
) -> list[Expense]:
    result = await db.execute(
        select(Expense)
        .where(
            Expense.group_id == group_id,
            Expense.is_deleted.is_(False),
        )
        .order_by(Expense.created_at.desc(), Expense.id.desc())
    )
    return list(result.scalars().all())


async def update_expense(
    db: AsyncSession,
    expense: Expense,
    *,
    description: str,
    amount: Decimal,
    payer_id: UUID,
    expense_date: date,
) -> Expense:
    expense.description = description
    expense.amount = amount
    expense.payer_id = payer_id
    expense.expense_date = expense_date
    await db.flush()
    await db.refresh(expense)
    return expense


async def soft_delete_expense(db: AsyncSession, expense: Expense) -> None:
    expense.is_deleted = True
    expense.deleted_at = datetime.now(timezone.utc)
    await db.flush()
