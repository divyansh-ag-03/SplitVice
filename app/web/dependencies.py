"""
Web-layer auth dependency.

Reads the access_token from an HttpOnly cookie (set on login).
Redirects to /login if the token is missing or invalid.
Kept separate from the API Bearer-token dependency.
"""

from fastapi import Cookie, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.repositories import user_repository as user_repo
from app.schemas.users import UserPublic


async def get_current_web_user(
    access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> UserPublic:
    """
    Validate the access_token cookie and return the current user.
    Raises HTTP 302 redirect to /login if the token is missing or invalid.
    """
    if not access_token:
        raise HTTPException(status_code=302, headers={"Location": "/login"})

    try:
        user_id = decode_access_token(access_token)
    except ValueError:
        raise HTTPException(status_code=302, headers={"Location": "/login"})

    user = await user_repo.get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=302, headers={"Location": "/login"})

    return UserPublic.model_validate(user)
