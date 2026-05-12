"""
Balance routes — thin request/response layer, no business logic.

GET /api/v1/groups/{group_id}/balances      group balance summary + simplified debts
GET /api/v1/groups/{group_id}/balances/me   current user's balance breakdown
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, get_db
from app.schemas.balances import GroupBalanceResponse, MyBalanceResponse
from app.schemas.users import UserPublic
from app.services import balance_service

router = APIRouter(prefix="/api/v1/groups", tags=["balances"])


@router.get("/{group_id}/balances", response_model=GroupBalanceResponse)
async def get_group_balances(
    group_id: UUID,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroupBalanceResponse:
    return await balance_service.get_group_balances(db, group_id, current_user.id)


@router.get("/{group_id}/balances/me", response_model=MyBalanceResponse)
async def get_my_balance(
    group_id: UUID,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MyBalanceResponse:
    return await balance_service.get_my_balance(db, group_id, current_user.id)
