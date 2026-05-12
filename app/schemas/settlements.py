from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class CreateSettlementRequest(BaseModel):
    payer_id: UUID
    payee_id: UUID
    amount: Decimal = Field(gt=0)
    settlement_date: date
    description: str | None = Field(default=None, max_length=500)


class SettlementSummary(BaseModel):
    """Lightweight settlement entry for list responses."""

    id: UUID
    payer_id: UUID
    payer_name: str
    payee_id: UUID
    payee_name: str
    amount: Decimal
    settlement_date: date
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SettlementDetail(BaseModel):
    """Full settlement detail."""

    id: UUID
    group_id: UUID
    payer_id: UUID
    payer_name: str
    payee_id: UUID
    payee_name: str
    creator_id: UUID
    creator_name: str
    amount: Decimal
    settlement_date: date
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
