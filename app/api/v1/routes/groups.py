"""
Group routes — thin request/response layer, no business logic.

POST   /api/v1/groups                              create group
GET    /api/v1/groups                              list user's groups
GET    /api/v1/groups/{group_id}                   group detail
PATCH  /api/v1/groups/{group_id}                   rename group
POST   /api/v1/groups/{group_id}/members           add member
DELETE /api/v1/groups/{group_id}/members/{user_id} remove member
POST   /api/v1/groups/{group_id}/leave             leave group
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, get_db
from app.schemas.groups import (
    AddMemberRequest,
    CreateGroupRequest,
    GroupDetail,
    GroupSummary,
    UpdateGroupRequest,
)
from app.schemas.users import UserPublic
from app.services import group_service

router = APIRouter(prefix="/api/v1/groups", tags=["groups"])


@router.post("", response_model=GroupDetail, status_code=status.HTTP_201_CREATED)
async def create_group(
    data: CreateGroupRequest,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroupDetail:
    result = await group_service.create_group(db, current_user.id, data)
    await db.commit()
    return result


@router.get("", response_model=list[GroupSummary])
async def list_groups(
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[GroupSummary]:
    return await group_service.list_user_groups(db, current_user.id)


@router.get("/{group_id}", response_model=GroupDetail)
async def get_group(
    group_id: UUID,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroupDetail:
    return await group_service.get_group(db, group_id, current_user.id)


@router.patch("/{group_id}", response_model=GroupDetail)
async def update_group(
    group_id: UUID,
    data: UpdateGroupRequest,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroupDetail:
    result = await group_service.update_group(db, group_id, current_user.id, data)
    await db.commit()
    return result


@router.post("/{group_id}/members", response_model=GroupDetail)
async def add_member(
    group_id: UUID,
    data: AddMemberRequest,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroupDetail:
    result = await group_service.add_member(db, group_id, current_user.id, data)
    await db.commit()
    return result


@router.delete("/{group_id}/members/{user_id}", response_model=GroupDetail)
async def remove_member(
    group_id: UUID,
    user_id: UUID,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroupDetail:
    result = await group_service.remove_member(db, group_id, current_user.id, user_id)
    await db.commit()
    return result


@router.post("/{group_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_group(
    group_id: UUID,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await group_service.leave_group(db, group_id, current_user.id)
    await db.commit()
