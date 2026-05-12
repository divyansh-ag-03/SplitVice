"""
Integration tests for the HTMX/Jinja2 web frontend.

Tests functional flows: auth, dashboard, group detail, expense creation,
settlement creation, and auth redirects. Does not assert HTML markup details.
"""

from datetime import date

import pytest
from httpx import AsyncClient

TODAY = str(date.today())


# ── Helpers ───────────────────────────────────────────────────────────────────


async def register_and_get_cookie(
    client: AsyncClient,
    *,
    name: str = "Alice",
    email: str = "alice@example.com",
    password: str = "password123",
) -> tuple[str, str]:
    """
    Register a user, log in via the web form.
    Returns (cookie_value, api_token) — both point to the same session.
    """
    await client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": password},
    )
    resp = await client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    assert resp.status_code == 302, f"Login failed: {resp.text}"
    cookie = resp.cookies.get("access_token")
    assert cookie, "No access_token cookie set after login"
    # The cookie value IS the access token — reuse it for API calls
    return cookie, cookie


def cookie_header(token: str) -> dict:
    return {"Cookie": f"access_token={token}"}


def api_auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def get_user_id_from_token(client: AsyncClient, token: str) -> str:
    resp = await client.get("/api/v1/users/me", headers=api_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


# ── Auth flow ─────────────────────────────────────────────────────────────────


async def test_login_page_renders(client: AsyncClient):
    resp = await client.get("/login")
    assert resp.status_code == 200
    assert b"Sign in" in resp.content


async def test_register_page_renders(client: AsyncClient):
    resp = await client.get("/register")
    assert resp.status_code == 200
    assert b"Create account" in resp.content


async def test_login_success_sets_cookie_and_redirects(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "password123"},
    )
    resp = await client.post(
        "/login",
        data={"email": "alice@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard"
    assert "access_token" in resp.cookies


async def test_login_wrong_password_shows_error(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "password123"},
    )
    resp = await client.post(
        "/login",
        data={"email": "alice@example.com", "password": "wrongpassword"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert b"Invalid" in resp.content or b"error" in resp.content.lower()


async def test_register_success_redirects_to_login(client: AsyncClient):
    resp = await client.post(
        "/register",
        data={"name": "Bob", "email": "bob@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/login" in resp.headers["location"]


async def test_register_duplicate_email_shows_error(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "password123"},
    )
    resp = await client.post(
        "/register",
        data={"name": "Alice2", "email": "alice@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert b"already" in resp.content.lower() or b"error" in resp.content.lower()


async def test_logout_clears_cookie_and_redirects(client: AsyncClient):
    cookie, _ = await register_and_get_cookie(client)
    resp = await client.post(
        "/logout",
        headers=cookie_header(cookie),
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/login" in resp.headers["location"]


# ── Auth redirects ────────────────────────────────────────────────────────────


async def test_dashboard_without_auth_redirects_to_login(client: AsyncClient):
    resp = await client.get("/dashboard", follow_redirects=False)
    assert resp.status_code in (302, 401)
    if resp.status_code == 302:
        assert "/login" in resp.headers["location"]


async def test_group_detail_without_auth_redirects_to_login(client: AsyncClient):
    resp = await client.get(
        "/groups/00000000-0000-0000-0000-000000000001", follow_redirects=False
    )
    assert resp.status_code in (302, 401)


async def test_root_without_auth_redirects_to_login(client: AsyncClient):
    resp = await client.get("/", follow_redirects=False)
    # Root now shows the landing page for unauthenticated users
    assert resp.status_code == 200


# ── Dashboard ─────────────────────────────────────────────────────────────────


async def test_dashboard_renders_for_authenticated_user(client: AsyncClient):
    cookie, _ = await register_and_get_cookie(client)
    resp = await client.get("/dashboard", headers=cookie_header(cookie))
    assert resp.status_code == 200
    assert b"SplitVice" in resp.content


async def test_dashboard_shows_user_groups(client: AsyncClient):
    cookie, api_token = await register_and_get_cookie(client)

    await client.post(
        "/api/v1/groups",
        json={"name": "Weekend Trip"},
        headers=api_auth(api_token),
    )

    resp = await client.get("/dashboard", headers=cookie_header(cookie))
    assert resp.status_code == 200
    assert b"Weekend Trip" in resp.content


# ── Group detail ──────────────────────────────────────────────────────────────


async def test_group_detail_renders(client: AsyncClient):
    cookie, api_token = await register_and_get_cookie(client)

    group_resp = await client.post(
        "/api/v1/groups",
        json={"name": "Flatmates"},
        headers=api_auth(api_token),
    )
    group_id = group_resp.json()["id"]

    resp = await client.get(f"/groups/{group_id}", headers=cookie_header(cookie))
    assert resp.status_code == 200
    assert b"Flatmates" in resp.content


async def test_group_detail_shows_expenses(client: AsyncClient):
    cookie, api_token = await register_and_get_cookie(client)
    alice_id = await get_user_id_from_token(client, api_token)

    group_resp = await client.post(
        "/api/v1/groups", json={"name": "Flatmates"}, headers=api_auth(api_token)
    )
    group_id = group_resp.json()["id"]

    await client.post(
        f"/api/v1/groups/{group_id}/expenses",
        json={
            "description": "Groceries",
            "amount": "50.00",
            "payer_id": alice_id,
            "expense_date": TODAY,
            "splits": [{"user_id": alice_id, "amount": "50.00"}],
        },
        headers=api_auth(api_token),
    )

    resp = await client.get(f"/groups/{group_id}", headers=cookie_header(cookie))
    assert resp.status_code == 200
    assert b"Groceries" in resp.content


# ── Expense creation via web form ─────────────────────────────────────────────


async def test_expense_form_renders(client: AsyncClient):
    cookie, api_token = await register_and_get_cookie(client)

    group_resp = await client.post(
        "/api/v1/groups", json={"name": "Test"}, headers=api_auth(api_token)
    )
    group_id = group_resp.json()["id"]

    resp = await client.get(
        f"/groups/{group_id}/expenses/new", headers=cookie_header(cookie)
    )
    assert resp.status_code == 200
    assert b"Add expense" in resp.content


async def test_expense_creation_via_form_redirects_to_group(client: AsyncClient):
    cookie, api_token = await register_and_get_cookie(client)
    alice_id = await get_user_id_from_token(client, api_token)

    group_resp = await client.post(
        "/api/v1/groups", json={"name": "Test"}, headers=api_auth(api_token)
    )
    group_id = group_resp.json()["id"]

    resp = await client.post(
        f"/groups/{group_id}/expenses",
        data={
            "description": "Dinner",
            "amount": "60.00",
            "payer_id": alice_id,
            "expense_date": TODAY,
            "split_user_ids": [alice_id],
            "split_amounts": ["60.00"],
        },
        headers=cookie_header(cookie),
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert f"/groups/{group_id}" in resp.headers["location"]


async def test_expense_creation_invalid_split_shows_error(client: AsyncClient):
    cookie, api_token = await register_and_get_cookie(client)
    alice_id = await get_user_id_from_token(client, api_token)

    group_resp = await client.post(
        "/api/v1/groups", json={"name": "Test"}, headers=api_auth(api_token)
    )
    group_id = group_resp.json()["id"]

    # Split amount (30) doesn't match total (60)
    resp = await client.post(
        f"/groups/{group_id}/expenses",
        data={
            "description": "Dinner",
            "amount": "60.00",
            "payer_id": alice_id,
            "expense_date": TODAY,
            "split_user_ids": [alice_id],
            "split_amounts": ["30.00"],
        },
        headers=cookie_header(cookie),
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert b"error" in resp.content.lower() or b"equal" in resp.content.lower() or b"split" in resp.content.lower()


# ── Settlement creation via web form ──────────────────────────────────────────


async def test_settlement_form_renders(client: AsyncClient):
    cookie, api_token = await register_and_get_cookie(client)

    group_resp = await client.post(
        "/api/v1/groups", json={"name": "Test"}, headers=api_auth(api_token)
    )
    group_id = group_resp.json()["id"]

    resp = await client.get(
        f"/groups/{group_id}/settlements/new", headers=cookie_header(cookie)
    )
    assert resp.status_code == 200
    assert b"settlement" in resp.content.lower()


async def test_settlement_creation_via_form(client: AsyncClient):
    """Full flow: expense → settlement via web form → redirect to group."""
    # Register Alice
    cookie_a, api_token_a = await register_and_get_cookie(
        client, name="Alice", email="alice@example.com"
    )
    alice_id = await get_user_id_from_token(client, api_token_a)

    # Register Bob (separate registration, no second login for Alice)
    await client.post(
        "/api/v1/auth/register",
        json={"name": "Bob", "email": "bob@example.com", "password": "password123"},
    )

    # Create group and add Bob
    group_resp = await client.post(
        "/api/v1/groups", json={"name": "Test"}, headers=api_auth(api_token_a)
    )
    group_id = group_resp.json()["id"]
    detail = await client.post(
        f"/api/v1/groups/{group_id}/members",
        json={"email": "bob@example.com"},
        headers=api_auth(api_token_a),
    )
    bob_id = next(
        m["user_id"] for m in detail.json()["members"] if m["email"] == "bob@example.com"
    )

    # Create expense: Alice pays $90, Bob owes $45
    await client.post(
        f"/api/v1/groups/{group_id}/expenses",
        json={
            "description": "Dinner",
            "amount": "90.00",
            "payer_id": alice_id,
            "expense_date": TODAY,
            "splits": [
                {"user_id": alice_id, "amount": "45.00"},
                {"user_id": bob_id, "amount": "45.00"},
            ],
        },
        headers=api_auth(api_token_a),
    )

    # Bob logs in via web form (fresh login, no duplicate hash)
    bob_login_resp = await client.post(
        "/login",
        data={"email": "bob@example.com", "password": "password123"},
        follow_redirects=False,
    )
    bob_cookie = bob_login_resp.cookies.get("access_token")
    assert bob_cookie, "Bob login failed"

    # Bob settles $45 via web form
    resp = await client.post(
        f"/groups/{group_id}/settlements",
        data={
            "payer_id": bob_id,
            "payee_id": alice_id,
            "amount": "45.00",
            "settlement_date": TODAY,
        },
        headers=cookie_header(bob_cookie),
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert f"/groups/{group_id}" in resp.headers["location"]
