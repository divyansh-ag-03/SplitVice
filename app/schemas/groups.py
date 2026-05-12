from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class UpdateGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class AddMemberRequest(BaseModel):
    email: str


class MemberOut(BaseModel):
    user_id: UUID
    name: str
    email: str
    role: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class GroupDetail(BaseModel):
    """Full group detail including member list."""

    id: UUID
    name: str
    description: str | None
    created_at: datetime
    current_user_role: str
    members: list[MemberOut]

    model_config = {"from_attributes": True}


class GroupSummary(BaseModel):
    """Lightweight group entry for the list endpoint."""

    id: UUID
    name: str
    description: str | None
    created_at: datetime
    current_user_role: str
    member_count: int
    # Placeholder — actual balance computation is Task 7
    user_balance: Decimal = Decimal("0.0000")

    model_config = {"from_attributes": True}
