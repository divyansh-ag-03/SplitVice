from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """
    An authenticated person with an account in the system.

    Relationships:
    - refresh_tokens: one-to-many. Cascade delete-orphan — when a User row is
      hard-deleted, all their RefreshToken rows are removed automatically.
      In normal operation users are never hard-deleted (only deactivated via
      is_active), but the cascade is a safety net.
    """

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,  # every login does WHERE email = ?
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"


class RefreshToken(Base):
    """
    A hashed refresh token tied to a user.

    Only the SHA-256 hash of the raw token is stored — the plaintext is never
    persisted. Tokens are looked up by hash on refresh and deleted on logout.

    Cascade: rows are deleted automatically when the parent User is deleted
    (via User.refresh_tokens cascade="all, delete-orphan").
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # logout: DELETE WHERE user_id = ? AND token_hash = ?
    )
    token_hash: Mapped[str] = mapped_column(
        String(255),
        unique=True,  # token hashes must be globally unique
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="refresh_tokens",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id} user_id={self.user_id}>"
