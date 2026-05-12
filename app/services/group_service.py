"""
Group service — all business logic for group and membership operations.

Routes call these functions. Repositories handle DB access.
The caller (route) is responsible for committing the transaction.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.repositories import group_repository as group_repo
from app.repositories import user_repository as user_repo
from app.schemas.groups import (
    AddMemberRequest,
    CreateGroupRequest,
    GroupDetail,
    GroupSummary,
    MemberOut,
    UpdateGroupRequest,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def user_has_nonzero_balance(
    db: AsyncSession, group_id: UUID, user_id: UUID
) -> bool:
    """Delegate to balance_service — imported here to avoid circular imports."""
    from app.services.balance_service import user_has_nonzero_balance as _check
    return await _check(db, group_id, user_id)


async def _require_group(db: AsyncSession, group_id: UUID):
    """Load a group or raise 404."""
    group = await group_repo.get_group_by_id(db, group_id)
    if group is None:
        raise NotFoundError("Group not found")
    return group


async def _require_membership(db: AsyncSession, group_id: UUID, user_id: UUID):
    """Load a membership or raise 403."""
    membership = await group_repo.get_membership(db, group_id, user_id)
    if membership is None:
        raise ForbiddenError("You are not a member of this group")
    return membership


async def _require_admin(db: AsyncSession, group_id: UUID, user_id: UUID):
    """Load a membership and assert admin role, or raise 403."""
    membership = await _require_membership(db, group_id, user_id)
    if membership.role != "admin":
        raise ForbiddenError("Only group admins can perform this action")
    return membership


async def _build_member_out(db: AsyncSession, member) -> MemberOut:
    """Load the user for a GroupMember and return a MemberOut schema."""
    user = await user_repo.get_user_by_id(db, member.user_id)
    return MemberOut(
        user_id=member.user_id,
        name=user.name if user else "Unknown",
        email=user.email if user else "",
        role=member.role,
        joined_at=member.joined_at,
    )


async def _build_group_detail(
    db: AsyncSession, group, current_user_id: UUID
) -> GroupDetail:
    members_orm = await group_repo.list_members(db, group.id)
    members_out = [await _build_member_out(db, m) for m in members_orm]
    current_membership = next(
        (m for m in members_orm if m.user_id == current_user_id), None
    )
    return GroupDetail(
        id=group.id,
        name=group.name,
        description=group.description,
        created_at=group.created_at,
        current_user_role=current_membership.role if current_membership else "member",
        members=members_out,
    )


# ── Service functions ─────────────────────────────────────────────────────────


async def create_group(
    db: AsyncSession,
    creator_id: UUID,
    data: CreateGroupRequest,
) -> GroupDetail:
    name = data.name.strip()
    if not name:
        raise ValidationError("Group name cannot be empty")

    group = await group_repo.create_group(db, name=name, description=data.description)
    await group_repo.add_member(db, group_id=group.id, user_id=creator_id, role="admin")

    return await _build_group_detail(db, group, creator_id)


async def list_user_groups(
    db: AsyncSession, user_id: UUID
) -> list[GroupSummary]:
    rows = await group_repo.list_user_groups(db, user_id)
    summaries = []
    for group, membership in rows:
        member_count = await group_repo.count_members(db, group.id)
        summaries.append(
            GroupSummary(
                id=group.id,
                name=group.name,
                description=group.description,
                created_at=group.created_at,
                current_user_role=membership.role,
                member_count=member_count,
            )
        )
    return summaries


async def get_group(
    db: AsyncSession, group_id: UUID, current_user_id: UUID
) -> GroupDetail:
    group = await _require_group(db, group_id)
    await _require_membership(db, group_id, current_user_id)
    return await _build_group_detail(db, group, current_user_id)


async def update_group(
    db: AsyncSession,
    group_id: UUID,
    current_user_id: UUID,
    data: UpdateGroupRequest,
) -> GroupDetail:
    group = await _require_group(db, group_id)
    await _require_admin(db, group_id, current_user_id)

    name = data.name.strip()
    if not name:
        raise ValidationError("Group name cannot be empty")

    group = await group_repo.update_group(db, group, name=name)
    return await _build_group_detail(db, group, current_user_id)


async def add_member(
    db: AsyncSession,
    group_id: UUID,
    current_user_id: UUID,
    data: AddMemberRequest,
) -> GroupDetail:
    await _require_group(db, group_id)
    await _require_admin(db, group_id, current_user_id)

    email = data.email.strip().lower()
    target_user = await user_repo.get_user_by_email(db, email)
    if target_user is None or not target_user.is_active:
        raise NotFoundError("No active user found with that email")

    existing = await group_repo.get_membership(db, group_id, target_user.id)
    if existing is not None:
        raise ConflictError("User is already a member of this group")

    await group_repo.add_member(
        db, group_id=group_id, user_id=target_user.id, role="member"
    )

    group = await group_repo.get_group_by_id(db, group_id)
    return await _build_group_detail(db, group, current_user_id)


async def remove_member(
    db: AsyncSession,
    group_id: UUID,
    current_user_id: UUID,
    target_user_id: UUID,
) -> GroupDetail:
    await _require_group(db, group_id)
    await _require_admin(db, group_id, current_user_id)

    if target_user_id == current_user_id:
        raise ForbiddenError("Use the leave endpoint to remove yourself from a group")

    target_membership = await group_repo.get_membership(db, group_id, target_user_id)
    if target_membership is None:
        raise NotFoundError("User is not a member of this group")

    if target_membership.role == "admin":
        admin_count = await group_repo.count_admins(db, group_id)
        if admin_count <= 1:
            raise ForbiddenError("Cannot remove the last admin from the group")

    if await user_has_nonzero_balance(db, group_id, target_user_id):
        raise ConflictError("Cannot remove a member with a non-zero balance")

    await group_repo.remove_member(db, group_id, target_user_id)

    group = await group_repo.get_group_by_id(db, group_id)
    return await _build_group_detail(db, group, current_user_id)


async def leave_group(
    db: AsyncSession,
    group_id: UUID,
    current_user_id: UUID,
) -> None:
    await _require_group(db, group_id)
    membership = await _require_membership(db, group_id, current_user_id)

    if membership.role == "admin":
        admin_count = await group_repo.count_admins(db, group_id)
        if admin_count <= 1:
            raise ForbiddenError(
                "You are the last admin. Assign another admin before leaving."
            )

    if await user_has_nonzero_balance(db, group_id, current_user_id):
        raise ConflictError("Cannot leave a group with a non-zero balance")

    await group_repo.remove_member(db, group_id, current_user_id)
