from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class ExpenseSplitRequest(BaseModel):
    user_id: UUID
    amount: Decimal = Field(gt=0)


class CreateExpenseRequest(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    amount: Decimal = Field(gt=0)
    payer_id: UUID
    expense_date: date
    splits: list[ExpenseSplitRequest] = Field(min_length=1)


class UpdateExpenseRequest(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    amount: Decimal = Field(gt=0)
    payer_id: UUID
    expense_date: date
    splits: list[ExpenseSplitRequest] = Field(min_length=1)


class ExpenseSplitOut(BaseModel):
    user_id: UUID
    name: str
    amount: Decimal

    model_config = {"from_attributes": True}


class ExpenseSummary(BaseModel):
    """Lightweight expense entry for list responses."""

    id: UUID
    description: str
    amount: Decimal
    payer_id: UUID
    payer_name: str
    creator_id: UUID
    creator_name: str
    expense_date: date
    created_at: datetime
    split_count: int

    model_config = {"from_attributes": True}


class ExpenseDetail(BaseModel):
    """Full expense detail including all splits."""

    id: UUID
    group_id: UUID
    description: str
    amount: Decimal
    payer_id: UUID
    payer_name: str
    creator_id: UUID
    creator_name: str
    expense_date: date
    created_at: datetime
    updated_at: datetime
    splits: list[ExpenseSplitOut]

    model_config = {"from_attributes": True}
