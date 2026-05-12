"""
FastAPI dependency factories for the v1 API.

get_db        — yields a database session (re-exported from db.session)
get_current_user — decodes the Bearer token and returns the authenticated user
"""

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.schemas.users import UserPublic
from app.services import auth_service

# tokenUrl points to the login endpoint — used by Swagger UI's "Authorize" button
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(_oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> UserPublic:
    """
    Decode the Bearer token and return the authenticated user's public profile.

    Raises HTTP 401 (via UnauthorizedError) if:
    - The token is missing, malformed, or expired
    - The user no longer exists or is inactive
    """
    try:
        user_id = decode_access_token(token)
    except ValueError as exc:
        raise UnauthorizedError("Invalid or expired access token") from exc

    return await auth_service.get_user_by_id(db, user_id)
