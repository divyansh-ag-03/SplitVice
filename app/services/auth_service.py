"""
Authentication service.

Contains all business logic for registration, login, token refresh, and logout.
Routes call these functions; repositories handle all DB access.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.repositories import user_repository as user_repo
from app.schemas.auth import AccessToken, LoginRequest, RegisterRequest, TokenPair
from app.schemas.users import UserPublic


async def register(db: AsyncSession, data: RegisterRequest) -> UserPublic:
    """
    Create a new user account.

    Raises ConflictError if the email is already registered.
    The caller must commit the transaction after this returns.
    """
    existing = await user_repo.get_user_by_email(db, data.email)
    if existing is not None:
        raise ConflictError("An account with this email already exists")

    user = await user_repo.create_user(
        db,
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
    )
    return UserPublic.model_validate(user)


async def login(db: AsyncSession, data: LoginRequest) -> TokenPair:
    """
    Authenticate a user and issue an access + refresh token pair.

    Always raises UnauthorizedError for both "user not found" and "wrong
    password" — never reveal which one failed.
    The caller must commit the transaction after this returns.
    """
    user = await user_repo.get_user_by_email(db, data.email)
    if user is None or not verify_password(data.password, user.password_hash):
        raise UnauthorizedError("Invalid email or password")

    raw_refresh = create_refresh_token(user.id)
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=7  # matches REFRESH_TOKEN_EXPIRE_DAYS default; settings used in security.py
    )
    await user_repo.create_refresh_token(
        db,
        user_id=user.id,
        token_hash=hash_token(raw_refresh),
        expires_at=expires_at,
    )

    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=raw_refresh,
    )


async def refresh(db: AsyncSession, raw_refresh_token: str) -> AccessToken:
    """
    Issue a new access token given a valid refresh token.

    Raises UnauthorizedError if the token is invalid, expired, or not found
    in the database (e.g. already logged out).
    Does NOT rotate the refresh token — the same refresh token stays valid
    until it expires or the user logs out.
    """
    # Validate the JWT signature and expiry first (cheap, no DB hit)
    try:
        user_id = decode_refresh_token(raw_refresh_token)
    except ValueError as exc:
        raise UnauthorizedError("Invalid or expired refresh token") from exc

    # Confirm the token is still in the DB (not logged out)
    stored = await user_repo.get_refresh_token_by_hash(
        db, hash_token(raw_refresh_token)
    )
    if stored is None:
        raise UnauthorizedError("Refresh token has been revoked")

    # Extra safety: check DB-level expiry (covers clock skew edge cases)
    # stored.expires_at may be timezone-naive (SQLite) or timezone-aware (PostgreSQL)
    now = datetime.now(timezone.utc)
    expires = stored.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        raise UnauthorizedError("Refresh token has expired")

    return AccessToken(access_token=create_access_token(user_id))


async def logout(db: AsyncSession, raw_refresh_token: str) -> None:
    """
    Invalidate a refresh token so it cannot be reused.

    Silently succeeds if the token is not found (already logged out).
    The caller must commit the transaction after this returns.
    """
    await user_repo.delete_refresh_token_by_hash(db, hash_token(raw_refresh_token))


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> UserPublic:
    """
    Load a user by id for the current-user dependency.

    Raises UnauthorizedError if the user does not exist or is inactive.
    """
    user = await user_repo.get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return UserPublic.model_validate(user)
