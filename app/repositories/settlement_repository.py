"""
Settlement data-access functions.

Thin DB layer — no business logic, no authorization, no balance logic.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settlement import Settlement


async def create_settlement(
    db: AsyncSession,
    *,
    group_id: UUID,
    payer_id: UUID,
    payee_id: UUID,
    creator_id: UUID,
    amount: Decimal,
    settlement_date: date,
    description: str | None,
) -> Settlement:
    settlement = Settlement(
        group_id=group_id,
        payer_id=payer_id,
        payee_id=payee_id,
        creator_id=creator_id,
        amount=amount,
        settlement_date=settlement_date,
        description=description,
    )
    db.add(settlement)
    await db.flush()
    await db.refresh(settlement)
    return settlement


async def get_settlement_by_id(
    db: AsyncSession, settlement_id: UUID
) -> Settlement | None:
    result = await db.execute(
        select(Settlement).where(
            Settlement.id == settlement_id,
            Settlement.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def list_group_settlements(
    db: AsyncSession, group_id: UUID
) -> list[Settlement]:
    result = await db.execute(
        select(Settlement)
        .where(
            Settlement.group_id == group_id,
            Settlement.is_deleted.is_(False),
        )
        .order_by(Settlement.created_at.desc(), Settlement.id.desc())
    )
    return list(result.scalars().all())


async def soft_delete_settlement(db: AsyncSession, settlement: Settlement) -> None:
    settlement.is_deleted = True
    settlement.deleted_at = datetime.now(timezone.utc)
    await db.flush()
