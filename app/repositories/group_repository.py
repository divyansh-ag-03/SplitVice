"""
Group and GroupMember data-access functions.

Thin DB layer — no business logic, no transaction ownership.
All functions accept an AsyncSession and return ORM objects or None.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group, GroupMember


# ── Group ─────────────────────────────────────────────────────────────────────


async def create_group(
    db: AsyncSession,
    *,
    name: str,
    description: str | None,
) -> Group:
    group = Group(name=name, description=description)
    db.add(group)
    await db.flush()
    await db.refresh(group)
    return group


async def get_group_by_id(db: AsyncSession, group_id: UUID) -> Group | None:
    result = await db.execute(
        select(Group).where(Group.id == group_id, Group.is_deleted.is_(False))
    )
    return result.scalar_one_or_none()


async def update_group(db: AsyncSession, group: Group, *, name: str) -> Group:
    group.name = name
    await db.flush()
    await db.refresh(group)
    return group


# ── GroupMember ───────────────────────────────────────────────────────────────


async def get_membership(
    db: AsyncSession, group_id: UUID, user_id: UUID
) -> GroupMember | None:
    result = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def add_member(
    db: AsyncSession,
    *,
    group_id: UUID,
    user_id: UUID,
    role: str,
) -> GroupMember:
    member = GroupMember(
        group_id=group_id,
        user_id=user_id,
        role=role,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(member)
    await db.flush()
    return member


async def remove_member(
    db: AsyncSession, group_id: UUID, user_id: UUID
) -> None:
    membership = await get_membership(db, group_id, user_id)
    if membership is not None:
        await db.delete(membership)
        await db.flush()


async def list_members(
    db: AsyncSession, group_id: UUID
) -> list[GroupMember]:
    result = await db.execute(
        select(GroupMember).where(GroupMember.group_id == group_id)
    )
    return list(result.scalars().all())


async def count_admins(db: AsyncSession, group_id: UUID) -> int:
    result = await db.execute(
        select(func.count()).where(
            GroupMember.group_id == group_id,
            GroupMember.role == "admin",
        )
    )
    return result.scalar_one()


async def list_user_groups(
    db: AsyncSession, user_id: UUID
) -> list[tuple[Group, GroupMember]]:
    """
    Return (Group, GroupMember) pairs for all active groups the user belongs to,
    ordered newest first.
    """
    result = await db.execute(
        select(Group, GroupMember)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .where(
            GroupMember.user_id == user_id,
            Group.is_deleted.is_(False),
        )
        .order_by(Group.created_at.desc(), Group.id.desc())
    )
    return list(result.all())


async def count_members(db: AsyncSession, group_id: UUID) -> int:
    result = await db.execute(
        select(func.count()).where(GroupMember.group_id == group_id)
    )
    return result.scalar_one()
