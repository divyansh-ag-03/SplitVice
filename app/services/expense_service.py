"""
Expense service — all business logic for expense operations.

Routes call these functions. Repositories handle DB access.
The caller (route) is responsible for committing the transaction.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.repositories import expense_repository as expense_repo
from app.repositories import group_repository as group_repo
from app.repositories import user_repository as user_repo
from app.schemas.expenses import (
    CreateExpenseRequest,
    ExpenseDetail,
    ExpenseSplitOut,
    ExpenseSummary,
    UpdateExpenseRequest,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _require_group_member(db: AsyncSession, group_id: UUID, user_id: UUID) -> None:
    """Raise ForbiddenError if user is not a member of the group."""
    membership = await group_repo.get_membership(db, group_id, user_id)
    if membership is None:
        raise ForbiddenError("You are not a member of this group")


async def _validate_splits(
    db: AsyncSession,
    group_id: UUID,
    expense_amount: Decimal,
    splits: list,
) -> None:
    """
    Validate split inputs:
    - No duplicate user_ids
    - All split users are group members
    - All split amounts > 0
    - Sum of splits equals expense amount exactly (Decimal comparison)
    """
    user_ids = [s.user_id for s in splits]
    if len(user_ids) != len(set(user_ids)):
        raise ValidationError("Duplicate users in splits are not allowed")

    for split in splits:
        if split.amount <= Decimal("0"):
            raise ValidationError("Split amounts must be greater than zero")
        membership = await group_repo.get_membership(db, group_id, split.user_id)
        if membership is None:
            raise ValidationError(
                f"Split user {split.user_id} is not a member of this group"
            )

    split_total = sum(s.amount for s in splits)
    if split_total != expense_amount:
        raise ValidationError(
            f"Split amounts ({split_total}) must equal expense total ({expense_amount})"
        )


async def _build_expense_detail(db: AsyncSession, expense) -> ExpenseDetail:
    splits_orm = await expense_repo.list_expense_splits(db, expense.id)

    splits_out = []
    for split in splits_orm:
        user = await user_repo.get_user_by_id(db, split.user_id)
        splits_out.append(
            ExpenseSplitOut(
                user_id=split.user_id,
                name=user.name if user else "Unknown",
                amount=split.amount,
            )
        )

    payer = await user_repo.get_user_by_id(db, expense.payer_id)
    creator = await user_repo.get_user_by_id(db, expense.created_by)

    return ExpenseDetail(
        id=expense.id,
        group_id=expense.group_id,
        description=expense.description,
        amount=expense.amount,
        payer_id=expense.payer_id,
        payer_name=payer.name if payer else "Unknown",
        creator_id=expense.created_by,
        creator_name=creator.name if creator else "Unknown",
        expense_date=expense.expense_date,
        created_at=expense.created_at,
        updated_at=expense.updated_at,
        splits=splits_out,
    )


async def _build_expense_summary(db: AsyncSession, expense) -> ExpenseSummary:
    splits_orm = await expense_repo.list_expense_splits(db, expense.id)
    payer = await user_repo.get_user_by_id(db, expense.payer_id)
    creator = await user_repo.get_user_by_id(db, expense.created_by)

    return ExpenseSummary(
        id=expense.id,
        description=expense.description,
        amount=expense.amount,
        payer_id=expense.payer_id,
        payer_name=payer.name if payer else "Unknown",
        creator_id=expense.created_by,
        creator_name=creator.name if creator else "Unknown",
        expense_date=expense.expense_date,
        created_at=expense.created_at,
        split_count=len(splits_orm),
    )


# ── Service functions ─────────────────────────────────────────────────────────


async def create_expense(
    db: AsyncSession,
    group_id: UUID,
    current_user_id: UUID,
    data: CreateExpenseRequest,
) -> ExpenseDetail:
    # Creator must be a group member
    await _require_group_member(db, group_id, current_user_id)

    # Payer must be a group member
    if await group_repo.get_membership(db, group_id, data.payer_id) is None:
        raise ValidationError("Payer is not a member of this group")

    description = data.description.strip()
    if not description:
        raise ValidationError("Description cannot be empty")

    await _validate_splits(db, group_id, data.amount, data.splits)

    # Persist expense + splits atomically (both flushed before caller commits)
    expense = await expense_repo.create_expense(
        db,
        group_id=group_id,
        payer_id=data.payer_id,
        created_by=current_user_id,
        description=description,
        amount=data.amount,
        expense_date=data.expense_date,
    )
    await expense_repo.create_expense_splits(
        db,
        expense.id,
        [(s.user_id, s.amount) for s in data.splits],
    )

    return await _build_expense_detail(db, expense)


async def list_group_expenses(
    db: AsyncSession,
    group_id: UUID,
    current_user_id: UUID,
) -> list[ExpenseSummary]:
    await _require_group_member(db, group_id, current_user_id)
    expenses = await expense_repo.list_group_expenses(db, group_id)
    return [await _build_expense_summary(db, e) for e in expenses]


async def get_expense(
    db: AsyncSession,
    expense_id: UUID,
    current_user_id: UUID,
) -> ExpenseDetail:
    expense = await expense_repo.get_expense_by_id(db, expense_id)
    if expense is None:
        raise NotFoundError("Expense not found")

    await _require_group_member(db, expense.group_id, current_user_id)
    return await _build_expense_detail(db, expense)


async def update_expense(
    db: AsyncSession,
    expense_id: UUID,
    current_user_id: UUID,
    data: UpdateExpenseRequest,
) -> ExpenseDetail:
    expense = await expense_repo.get_expense_by_id(db, expense_id)
    if expense is None:
        raise NotFoundError("Expense not found")

    if expense.created_by != current_user_id:
        raise ForbiddenError("Only the expense creator can edit this expense")

    if await group_repo.get_membership(db, expense.group_id, data.payer_id) is None:
        raise ValidationError("Payer is not a member of this group")

    description = data.description.strip()
    if not description:
        raise ValidationError("Description cannot be empty")

    await _validate_splits(db, expense.group_id, data.amount, data.splits)

    # Replace splits: delete old, insert new, update expense fields — all in one flush
    await expense_repo.delete_expense_splits(db, expense.id)
    await expense_repo.create_expense_splits(
        db,
        expense.id,
        [(s.user_id, s.amount) for s in data.splits],
    )
    expense = await expense_repo.update_expense(
        db,
        expense,
        description=description,
        amount=data.amount,
        payer_id=data.payer_id,
        expense_date=data.expense_date,
    )

    return await _build_expense_detail(db, expense)


async def delete_expense(
    db: AsyncSession,
    expense_id: UUID,
    current_user_id: UUID,
) -> None:
    expense = await expense_repo.get_expense_by_id(db, expense_id)
    if expense is None:
        raise NotFoundError("Expense not found")

    if expense.created_by != current_user_id:
        raise ForbiddenError("Only the expense creator can delete this expense")

    await expense_repo.soft_delete_expense(db, expense)
