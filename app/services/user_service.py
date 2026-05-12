"""
User profile service.

Handles profile reads and updates. Avatar upload is deferred to v2.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.repositories import user_repository as user_repo
from app.schemas.users import UpdateProfileRequest, UserPublic


async def get_profile(db: AsyncSession, user_id: UUID) -> UserPublic:
    """Return the public profile for the given user id."""
    from app.core.exceptions import NotFoundError

    user = await user_repo.get_user_by_id(db, user_id)
    if user is None:
        raise NotFoundError("User not found")
    return UserPublic.model_validate(user)


async def update_profile(
    db: AsyncSession,
    *,
    current_user_id: UUID,
    target_user_id: UUID,
    data: UpdateProfileRequest,
) -> UserPublic:
    """
    Update a user's profile.

    Raises ForbiddenError if current_user_id != target_user_id.
    The caller must commit the transaction after this returns.
    """
    if current_user_id != target_user_id:
        raise ForbiddenError("You can only update your own profile")

    from app.core.exceptions import NotFoundError

    user = await user_repo.get_user_by_id(db, target_user_id)
    if user is None:
        raise NotFoundError("User not found")

    user = await user_repo.update_user(db, user, name=data.name)
    return UserPublic.model_validate(user)
