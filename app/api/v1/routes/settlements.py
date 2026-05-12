"""
Settlement routes — thin request/response layer, no business logic.

POST   /api/v1/groups/{group_id}/settlements          create settlement
GET    /api/v1/groups/{group_id}/settlements          list group settlements
GET    /api/v1/settlements/{settlement_id}            settlement detail
DELETE /api/v1/settlements/{settlement_id}            soft-delete settlement
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, get_db
from app.schemas.settlements import (
    CreateSettlementRequest,
    SettlementDetail,
    SettlementSummary,
)
from app.schemas.users import UserPublic
from app.services import settlement_service

router = APIRouter(tags=["settlements"])


@router.post(
    "/api/v1/groups/{group_id}/settlements",
    response_model=SettlementDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_settlement(
    group_id: UUID,
    data: CreateSettlementRequest,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SettlementDetail:
    result = await settlement_service.create_settlement(db, group_id, current_user.id, data)
    await db.commit()
    return result


@router.get(
    "/api/v1/groups/{group_id}/settlements",
    response_model=list[SettlementSummary],
)
async def list_settlements(
    group_id: UUID,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SettlementSummary]:
    return await settlement_service.list_group_settlements(db, group_id, current_user.id)


@router.get(
    "/api/v1/settlements/{settlement_id}",
    response_model=SettlementDetail,
)
async def get_settlement(
    settlement_id: UUID,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SettlementDetail:
    return await settlement_service.get_settlement(db, settlement_id, current_user.id)


@router.delete(
    "/api/v1/settlements/{settlement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_settlement(
    settlement_id: UUID,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await settlement_service.delete_settlement(db, settlement_id, current_user.id)
    await db.commit()
