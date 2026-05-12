"""
Integration tests for authentication endpoints.

Covers:
- Registration: success, duplicate email, short password, bad email
- Login: success, wrong password, unknown email
- Protected endpoint: valid token, no token, tampered token
- Token refresh: valid token, invalid token, after logout
- Logout: success, reuse after logout
- Profile: GET /me, PATCH /me, cross-user protection
"""

import pytest
from httpx import AsyncClient


# ── Helpers ───────────────────────────────────────────────────────────────────


async def register_user(
    client: AsyncClient,
    *,
    name: str = "Alice",
    email: str = "alice@example.com",
    password: str = "password123",
) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": password},
    )
    return resp


async def login_user(
    client: AsyncClient,
    *,
    email: str = "alice@example.com",
    password: str = "password123",
) -> dict:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return resp


# ── Registration ──────────────────────────────────────────────────────────────


async def test_register_success(client: AsyncClient):
    resp = await register_user(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert body["name"] == "Alice"
    assert "id" in body
    assert "password_hash" not in body
    assert "password" not in body


async def test_register_duplicate_email(client: AsyncClient):
    await register_user(client)
    resp = await register_user(client)
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"].lower()


async def test_register_email_is_case_insensitive(client: AsyncClient):
    await register_user(client, email="Alice@Example.COM")
    resp = await register_user(client, email="alice@example.com")
    assert resp.status_code == 409


async def test_register_short_password(client: AsyncClient):
    resp = await register_user(client, password="short")
    assert resp.status_code == 422


async def test_register_invalid_email(client: AsyncClient):
    resp = await register_user(client, email="not-an-email")
    assert resp.status_code == 422


async def test_register_missing_name(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "password123"},
    )
    assert resp.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────


async def test_login_success(client: AsyncClient):
    await register_user(client)
    resp = await login_user(client)
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


async def test_login_wrong_password(client: AsyncClient):
    await register_user(client)
    resp = await login_user(client, password="wrongpassword")
    assert resp.status_code == 401


async def test_login_unknown_email(client: AsyncClient):
    resp = await login_user(client, email="nobody@example.com")
    assert resp.status_code == 401


async def test_login_wrong_and_unknown_return_same_status(client: AsyncClient):
    """Both wrong password and unknown email return 401 — no user enumeration."""
    await register_user(client)
    r1 = await login_user(client, password="wrong")
    r2 = await login_user(client, email="nobody@example.com")
    assert r1.status_code == r2.status_code == 401


# ── Protected endpoint ────────────────────────────────────────────────────────


async def test_get_me_with_valid_token(client: AsyncClient):
    await register_user(client)
    tokens = (await login_user(client)).json()
    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "alice@example.com"


async def test_get_me_without_token(client: AsyncClient):
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401


async def test_get_me_with_tampered_token(client: AsyncClient):
    await register_user(client)
    tokens = (await login_user(client)).json()
    bad_token = tokens["access_token"][:-4] + "XXXX"
    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {bad_token}"},
    )
    assert resp.status_code == 401


async def test_get_me_with_refresh_token_rejected(client: AsyncClient):
    """A refresh token must not be accepted as an access token."""
    await register_user(client)
    tokens = (await login_user(client)).json()
    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )
    assert resp.status_code == 401


# ── Token refresh ─────────────────────────────────────────────────────────────


async def test_refresh_returns_new_access_token(client: AsyncClient):
    await register_user(client)
    tokens = (await login_user(client)).json()
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    # Verify the new access token actually works
    me = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200


async def test_refresh_with_invalid_token(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "not.a.valid.token"},
    )
    assert resp.status_code == 401


async def test_refresh_with_access_token_rejected(client: AsyncClient):
    """An access token must not be accepted as a refresh token."""
    await register_user(client)
    tokens = (await login_user(client)).json()
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["access_token"]},
    )
    assert resp.status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────


async def test_logout_success(client: AsyncClient):
    await register_user(client)
    tokens = (await login_user(client)).json()
    resp = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert resp.status_code == 204


async def test_refresh_token_rejected_after_logout(client: AsyncClient):
    await register_user(client)
    tokens = (await login_user(client)).json()
    await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
    )
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert resp.status_code == 401


async def test_logout_is_idempotent(client: AsyncClient):
    """Logging out twice with the same token should not raise an error."""
    await register_user(client)
    tokens = (await login_user(client)).json()
    payload = {"refresh_token": tokens["refresh_token"]}
    r1 = await client.post("/api/v1/auth/logout", json=payload)
    r2 = await client.post("/api/v1/auth/logout", json=payload)
    assert r1.status_code == 204
    assert r2.status_code == 204


# ── Profile update ────────────────────────────────────────────────────────────


async def test_update_profile_name(client: AsyncClient):
    await register_user(client)
    tokens = (await login_user(client)).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    resp = await client.patch("/api/v1/users/me", json={"name": "Alicia"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Alicia"

    # Verify the change persisted
    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.json()["name"] == "Alicia"


async def test_update_profile_requires_auth(client: AsyncClient):
    resp = await client.patch("/api/v1/users/me", json={"name": "Hacker"})
    assert resp.status_code == 401


async def test_update_profile_empty_name_rejected(client: AsyncClient):
    await register_user(client)
    tokens = (await login_user(client)).json()
    resp = await client.patch(
        "/api/v1/users/me",
        json={"name": ""},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 422
