from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Group(Base, TimestampMixin):
    """
    A named collection of users who share expenses together.

    Soft-deleted via is_deleted + deleted_at rather than hard DELETE so that
    historical expense and settlement records remain intact and auditable.

    Relationships:
    - members: one-to-many to GroupMember. cascade="all, delete-orphan" so
      membership rows are cleaned up if a group is ever hard-deleted (rare in
      practice — groups are soft-deleted — but safe as a DB-level guarantee).
    """

    __tablename__ = "groups"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    members: Mapped[list["GroupMember"]] = relationship(
        "GroupMember",
        back_populates="group",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Group id={self.id} name={self.name!r}>"


class GroupMember(Base):
    """
    The join table between User and Group, with an added role column.

    Uses a composite primary key (group_id, user_id) — this is the natural
    key and also enforces the uniqueness constraint at the DB level without
    needing a separate surrogate id column or UniqueConstraint.

    role is either "admin" or "member". The group creator is always "admin".
    Only admins can add/remove members and delete the group.

    FK behaviour:
    - group_id CASCADE: membership rows are removed when a group is hard-deleted.
    - user_id RESTRICT: a user cannot be deleted while they have memberships.
      The service layer must remove memberships (after verifying zero balance)
      before a user account can be closed.
    """

    __tablename__ = "group_members"

    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        # "admin" | "member" — validated at the service layer
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        # set explicitly in the service layer so it's always accurate
    )

    # Relationships
    group: Mapped["Group"] = relationship(
        "Group",
        back_populates="members",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<GroupMember group={self.group_id} user={self.user_id} role={self.role!r}>"
