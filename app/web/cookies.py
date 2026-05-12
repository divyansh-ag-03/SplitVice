"""
Cookie helpers for web auth.

Sets and clears the access_token HttpOnly cookie.
The `secure` flag is enabled automatically in production (ENV=production).
"""

from fastapi.responses import Response

from app.core.config import settings

_COOKIE_NAME = "access_token"
_MAX_AGE = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def set_auth_cookie(response: Response, access_token: str) -> None:
    """Write the access token into an HttpOnly cookie."""
    response.set_cookie(
        key=_COOKIE_NAME,
        value=access_token,
        max_age=_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,  # True in production (HTTPS required)
    )


def clear_auth_cookie(response: Response) -> None:
    """Delete the access token cookie."""
    response.delete_cookie(
        key=_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )
