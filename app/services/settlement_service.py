"""
Settlement service — all business logic for settlement operations.

Key rules:
- Settlements are immutable financial records (no editing).
- Balances are always derived dynamically — this service never mutates them.
- Pairwise debt validation: payer must owe payee, amount cannot exceed debt.
- Only the creator can soft-delete a settlement.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.repositories import group_repository as group_repo
from app.repositories import settlement_repository as settlement_repo
from app.repositories import user_repository as user_repo
from app.schemas.settlements import (
    CreateSettlementRequest,
    SettlementDetail,
    SettlementSummary,
)
from app.services import balance_service

ZERO = Decimal("0.0000")


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _require_group_member(db: AsyncSession, group_id: UUID, user_id: UUID) -> None:
    membership = await group_repo.get_membership(db, group_id, user_id)
    if membership is None:
        raise ForbiddenError("You are not a member of this group")


async def _build_summary(db: AsyncSession, s) -> SettlementSummary:
    payer = await user_repo.get_user_by_id(db, s.payer_id)
    payee = await user_repo.get_user_by_id(db, s.payee_id)
    return SettlementSummary(
        id=s.id,
        payer_id=s.payer_id,
        payer_name=payer.name if payer else "Unknown",
        payee_id=s.payee_id,
        payee_name=payee.name if payee else "Unknown",
        amount=s.amount,
        settlement_date=s.settlement_date,
        description=s.description,
        created_at=s.created_at,
    )


async def _build_detail(db: AsyncSession, s) -> SettlementDetail:
    payer = await user_repo.get_user_by_id(db, s.payer_id)
    payee = await user_repo.get_user_by_id(db, s.payee_id)
    creator = await user_repo.get_user_by_id(db, s.creator_id)
    return SettlementDetail(
        id=s.id,
        group_id=s.group_id,
        payer_id=s.payer_id,
        payer_name=payer.name if payer else "Unknown",
        payee_id=s.payee_id,
        payee_name=payee.name if payee else "Unknown",
        creator_id=s.creator_id,
        creator_name=creator.name if creator else "Unknown",
        amount=s.amount,
        settlement_date=s.settlement_date,
        description=s.description,
        created_at=s.created_at,
    )


async def _find_debt_owed(
    db: AsyncSession,
    group_id: UUID,
    payer_id: UUID,
    payee_id: UUID,
    current_user_id: UUID,
) -> Decimal:
    """
    Return how much payer currently owes payee in this group.

    Uses the simplified debt list from balance_service — the same source
    of truth used everywhere else. Returns ZERO if no debt exists.
    """
    balance_response = await balance_service.get_group_balances(
        db, group_id, current_user_id
    )
    for debt in balance_response.simplified_debts:
        if debt.from_user_id == payer_id and debt.to_user_id == payee_id:
            return debt.amount
    return ZERO


# ── Service functions ─────────────────────────────────────────────────────────


async def create_settlement(
    db: AsyncSession,
    group_id: UUID,
    current_user_id: UUID,
    data: CreateSettlementRequest,
) -> SettlementDetail:
    # Creator must be a group member
    await _require_group_member(db, group_id, current_user_id)

    # Payer and payee must be group members
    if await group_repo.get_membership(db, group_id, data.payer_id) is None:
        raise ValidationError("Payer is not a member of this group")
    if await group_repo.get_membership(db, group_id, data.payee_id) is None:
        raise ValidationError("Payee is not a member of this group")

    # Cannot settle with yourself
    if data.payer_id == data.payee_id:
        raise ValidationError("Payer and payee cannot be the same user")

    # Trim description
    description = data.description.strip() if data.description else None

    # Pairwise debt validation: payer must owe payee, amount cannot exceed debt
    debt_owed = await _find_debt_owed(
        db, group_id, data.payer_id, data.payee_id, current_user_id
    )
    if debt_owed == ZERO:
        raise ConflictError(
            "No debt exists from payer to payee in this group"
        )
    if data.amount > debt_owed:
        raise ConflictError(
            f"Settlement amount ({data.amount}) exceeds current debt ({debt_owed})"
        )

    settlement = await settlement_repo.create_settlement(
        db,
        group_id=group_id,
        payer_id=data.payer_id,
        payee_id=data.payee_id,
        creator_id=current_user_id,
        amount=data.amount,
        settlement_date=data.settlement_date,
        description=description,
    )

    return await _build_detail(db, settlement)


async def list_group_settlements(
    db: AsyncSession,
    group_id: UUID,
    current_user_id: UUID,
) -> list[SettlementSummary]:
    await _require_group_member(db, group_id, current_user_id)
    settlements = await settlement_repo.list_group_settlements(db, group_id)
    return [await _build_summary(db, s) for s in settlements]


async def get_settlement(
    db: AsyncSession,
    settlement_id: UUID,
    current_user_id: UUID,
) -> SettlementDetail:
    settlement = await settlement_repo.get_settlement_by_id(db, settlement_id)
    if settlement is None:
        raise NotFoundError("Settlement not found")

    await _require_group_member(db, settlement.group_id, current_user_id)
    return await _build_detail(db, settlement)


async def delete_settlement(
    db: AsyncSession,
    settlement_id: UUID,
    current_user_id: UUID,
) -> None:
    settlement = await settlement_repo.get_settlement_by_id(db, settlement_id)
    if settlement is None:
        raise NotFoundError("Settlement not found")

    if settlement.creator_id != current_user_id:
        raise ForbiddenError("Only the settlement creator can delete this settlement")

    await settlement_repo.soft_delete_settlement(db, settlement)
