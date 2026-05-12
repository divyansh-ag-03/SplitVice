"""
Authentication routes.

POST /api/v1/auth/register  — create a new account
POST /api/v1/auth/login     — get access + refresh tokens
POST /api/v1/auth/refresh   — exchange a refresh token for a new access token
POST /api/v1/auth/logout    — invalidate a refresh token

No business logic lives here — routes validate input, call the service,
commit the transaction, and return the response.

Transaction pattern: call the service (which uses db.flush() internally),
then commit. On any AppException the session is not committed and the
exception handler returns the appropriate error response. SQLAlchemy rolls
back automatically when the session is closed without a commit.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_db
from app.schemas.auth import AccessToken, LoginRequest, RefreshRequest, RegisterRequest, TokenPair
from app.schemas.users import UserPublic
from app.services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserPublic:
    result = await auth_service.register(db, data)
    await db.commit()
    return result


@router.post("/login", response_model=TokenPair)
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    result = await auth_service.login(db, data)
    await db.commit()
    return result


@router.post("/refresh", response_model=AccessToken)
async def refresh_token(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> AccessToken:
    # refresh() is read-only — no commit needed
    return await auth_service.refresh(db, data.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    await auth_service.logout(db, data.refresh_token)
    await db.commit()
