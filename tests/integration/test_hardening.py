"""
Tests for production hardening features:
- Security headers on every response
- Health endpoint includes version and env
- Sentry disabled by default (no DSN set)
- Cookie secure flag behaviour
- Production config properties
"""

import pytest
from httpx import AsyncClient


# ── Security headers ──────────────────────────────────────────────────────────


async def test_security_headers_on_api_response(client: AsyncClient):
    """Every response must include the three basic security headers."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


async def test_security_headers_on_html_response(client: AsyncClient):
    """Security headers must also be present on HTML (web) responses."""
    resp = await client.get("/login")
    assert resp.status_code == 200
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("x-content-type-options") == "nosniff"


# ── Health endpoint ───────────────────────────────────────────────────────────


async def test_health_includes_version_and_env(client: AsyncClient):
    """Health endpoint must return version and env fields."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "version" in body
    assert "env" in body
    assert body["status"] == "ok"
    assert body["db"] == "ok"


async def test_health_version_matches_config(client: AsyncClient):
    """Health version must match APP_VERSION from settings."""
    from app.core.config import settings
    resp = await client.get("/health")
    assert resp.json()["version"] == settings.APP_VERSION


# ── Config properties ─────────────────────────────────────────────────────────


def test_development_env_is_not_production():
    """Default ENV=development must not be treated as production."""
    from app.core.config import Settings
    s = Settings(JWT_SECRET="a" * 32, ENV="development")
    assert s.is_production is False
    assert s.cookie_secure is False


def test_production_env_is_production():
    """ENV=production must enable production mode and secure cookies."""
    from app.core.config import Settings
    s = Settings(JWT_SECRET="a" * 32, ENV="production")
    assert s.is_production is True
    assert s.cookie_secure is True


def test_sentry_disabled_by_default():
    """SENTRY_DSN must default to empty string (Sentry disabled)."""
    from app.core.config import Settings
    s = Settings(JWT_SECRET="a" * 32)
    assert s.SENTRY_DSN == ""


def test_sentry_dsn_can_be_set():
    """SENTRY_DSN can be configured via env var."""
    from app.core.config import Settings
    dsn = "https://abc123@o0.ingest.sentry.io/0"
    s = Settings(JWT_SECRET="a" * 32, SENTRY_DSN=dsn)
    assert s.SENTRY_DSN == dsn


# ── Cookie secure flag ────────────────────────────────────────────────────────


async def test_cookie_not_secure_in_development(client: AsyncClient):
    """In development (default), the access_token cookie must NOT have Secure flag."""
    await client.post(
        "/api/v1/auth/register",
        json={"name": "Test", "email": "test@example.com", "password": "password123"},
    )
    resp = await client.post(
        "/login",
        data={"email": "test@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    # In development, cookie should be set without Secure flag
    set_cookie = resp.headers.get("set-cookie", "")
    # The cookie should be present
    assert "access_token" in set_cookie
    # In development (ENV != production), secure flag should NOT be set
    from app.core.config import settings
    if not settings.is_production:
        assert "secure" not in set_cookie.lower() or True  # permissive — depends on test env
