from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    Shared declarative base for all SQLAlchemy models.

    All models must inherit from this class so that Alembic's autogenerate
    can discover them via Base.metadata.
    """
    pass


class TimestampMixin:
    """
    Adds created_at and updated_at columns to any model.

    - created_at: set once by the DB on INSERT, never changes.
    - updated_at: set by the DB on INSERT and updated on every ORM-level UPDATE.

    IMPORTANT: onupdate=func.now() only fires when SQLAlchemy issues an ORM
    UPDATE statement. Bulk updates via session.execute(update(...).values(...))
    will NOT update this column automatically. Always use ORM-level updates
    (load the object, mutate it, flush) to keep updated_at accurate.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
