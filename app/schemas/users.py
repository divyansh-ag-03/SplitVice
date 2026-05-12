from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserPublic(BaseModel):
    """Public-facing user profile. Never includes password_hash."""

    id: UUID
    name: str
    email: EmailStr
    avatar_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateProfileRequest(BaseModel):
    """Fields the user may update on their own profile."""

    name: str = Field(min_length=1, max_length=255)
