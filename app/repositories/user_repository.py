"""
User and RefreshToken data-access functions.

All functions accept an AsyncSession and return ORM objects or None.
No business logic here — only DB reads and writes.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import RefreshToken, User


# ── User ──────────────────────────────────────────────────────────────────────


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(
        select(User).where(User.email == email.lower())
    )
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    *,
    name: str,
    email: str,
    password_hash: str,
) -> User:
    user = User(name=name, email=email.lower(), password_hash=password_hash)
    db.add(user)
    await db.flush()  # populate id and server defaults without committing
    await db.refresh(user)
    return user


async def update_user(db: AsyncSession, user: User, **fields: object) -> User:
    for key, value in fields.items():
        setattr(user, key, value)
    await db.flush()
    await db.refresh(user)
    return user


# ── RefreshToken ──────────────────────────────────────────────────────────────


async def create_refresh_token(
    db: AsyncSession,
    *,
    user_id: UUID,
    token_hash: str,
    expires_at: datetime,
) -> RefreshToken:
    token = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    db.add(token)
    await db.flush()
    return token


async def get_refresh_token_by_hash(
    db: AsyncSession, token_hash: str
) -> RefreshToken | None:
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    return result.scalar_one_or_none()


async def delete_refresh_token_by_hash(
    db: AsyncSession, token_hash: str
) -> None:
    await db.execute(
        delete(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
