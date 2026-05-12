"""
JWT and password hashing utilities.

All functions here are pure — no database access, no FastAPI dependencies.
They are imported by the auth service and the get_current_user dependency.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# JWT claim key for the subject (user id)
_SUBJECT_KEY = "sub"
# JWT claim key for the token type ("access" or "refresh")
_TYPE_KEY = "type"


# ── Password hashing ──────────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of the plaintext password."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the bcrypt hash, False otherwise."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── Refresh token hashing ─────────────────────────────────────────────────────


def hash_token(raw_token: str) -> str:
    """
    Return a SHA-256 hex digest of the raw refresh token string.

    We store only the hash in the DB — the raw token is sent to the client
    and never persisted. On refresh/logout we hash the incoming token and
    look up the hash.
    """
    return hashlib.sha256(raw_token.encode()).hexdigest()


# ── JWT creation ──────────────────────────────────────────────────────────────


def create_access_token(user_id: UUID) -> str:
    """
    Create a signed JWT access token for the given user.

    Expires in ACCESS_TOKEN_EXPIRE_MINUTES (default 15 min).
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        _SUBJECT_KEY: str(user_id),
        _TYPE_KEY: "access",
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: UUID) -> str:
    """
    Create a signed JWT refresh token for the given user.

    Expires in REFRESH_TOKEN_EXPIRE_DAYS (default 7 days).
    The raw token string is returned to the caller; only its hash is stored in DB.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        _SUBJECT_KEY: str(user_id),
        _TYPE_KEY: "refresh",
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


# ── JWT decoding ──────────────────────────────────────────────────────────────


def decode_access_token(token: str) -> UUID:
    """
    Decode and validate a JWT access token.

    Returns the user_id (UUID) from the subject claim.
    Raises ValueError on any validation failure (expired, tampered, wrong type).
    Callers should catch ValueError and raise their domain exception (UnauthorizedError).
    """
    return _decode_token(token, expected_type="access")


def decode_refresh_token(token: str) -> UUID:
    """
    Decode and validate a JWT refresh token.

    Returns the user_id (UUID) from the subject claim.
    Raises ValueError on any validation failure.
    """
    return _decode_token(token, expected_type="refresh")


def _decode_token(token: str, expected_type: str) -> UUID:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc

    token_type = payload.get(_TYPE_KEY)
    if token_type != expected_type:
        raise ValueError(
            f"Wrong token type: expected '{expected_type}', got '{token_type}'"
        )

    subject = payload.get(_SUBJECT_KEY)
    if not subject:
        raise ValueError("Token missing subject claim")

    try:
        return UUID(subject)
    except ValueError as exc:
        raise ValueError(f"Token subject is not a valid UUID: {subject}") from exc
