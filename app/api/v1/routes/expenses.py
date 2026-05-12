"""
Expense routes — thin request/response layer, no business logic.

POST   /api/v1/groups/{group_id}/expenses          create expense
GET    /api/v1/groups/{group_id}/expenses          list group expenses
GET    /api/v1/expenses/{expense_id}               expense detail
PATCH  /api/v1/expenses/{expense_id}               update expense
DELETE /api/v1/expenses/{expense_id}               soft-delete expense
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, get_db
from app.schemas.expenses import (
    CreateExpenseRequest,
    ExpenseDetail,
    ExpenseSummary,
    UpdateExpenseRequest,
)
from app.schemas.users import UserPublic
from app.services import expense_service

router = APIRouter(tags=["expenses"])


@router.post(
    "/api/v1/groups/{group_id}/expenses",
    response_model=ExpenseDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_expense(
    group_id: UUID,
    data: CreateExpenseRequest,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseDetail:
    result = await expense_service.create_expense(db, group_id, current_user.id, data)
    await db.commit()
    return result


@router.get(
    "/api/v1/groups/{group_id}/expenses",
    response_model=list[ExpenseSummary],
)
async def list_expenses(
    group_id: UUID,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ExpenseSummary]:
    return await expense_service.list_group_expenses(db, group_id, current_user.id)


@router.get(
    "/api/v1/expenses/{expense_id}",
    response_model=ExpenseDetail,
)
async def get_expense(
    expense_id: UUID,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseDetail:
    return await expense_service.get_expense(db, expense_id, current_user.id)


@router.patch(
    "/api/v1/expenses/{expense_id}",
    response_model=ExpenseDetail,
)
async def update_expense(
    expense_id: UUID,
    data: UpdateExpenseRequest,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseDetail:
    result = await expense_service.update_expense(db, expense_id, current_user.id, data)
    await db.commit()
    return result


@router.delete(
    "/api/v1/expenses/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_expense(
    expense_id: UUID,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await expense_service.delete_expense(db, expense_id, current_user.id)
    await db.commit()
