"""
User profile routes.

GET  /api/v1/users/me       — return the authenticated user's profile
PATCH /api/v1/users/me      — update name (avatar upload deferred to v2)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, get_db
from app.schemas.users import UpdateProfileRequest, UserPublic
from app.services import user_service

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me", response_model=UserPublic)
async def get_me(current_user: UserPublic = Depends(get_current_user)) -> UserPublic:
    return current_user


@router.patch("/me", response_model=UserPublic)
async def update_me(
    data: UpdateProfileRequest,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserPublic:
    result = await user_service.update_profile(
        db,
        current_user_id=current_user.id,
        target_user_id=current_user.id,
        data=data,
    )
    await db.commit()
    return result
