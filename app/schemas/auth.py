from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenPair(BaseModel):
    """Returned on successful login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessToken(BaseModel):
    """Returned on successful token refresh."""

    access_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
