"""
Small auth helpers shared across integration tests.

Keep these minimal — tests should remain explicit and readable.
These helpers only handle the repetitive register+login boilerplate.
"""

from datetime import date

from httpx import AsyncClient

TODAY = str(date.today())


async def register(
    client: AsyncClient,
    *,
    name: str,
    email: str,
    password: str = "password123",
) -> None:
    """Register a user via the API. Asserts 201."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": password},
    )
    assert resp.status_code == 201, f"Register failed for {email}: {resp.text}"


async def login(
    client: AsyncClient,
    *,
    email: str,
    password: str = "password123",
) -> str:
    """Login via the API and return the access token."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text}"
    return resp.json()["access_token"]


async def register_and_login(
    client: AsyncClient,
    *,
    name: str,
    email: str,
    password: str = "password123",
) -> str:
    """Register then login. Returns access token."""
    await register(client, name=name, email=email, password=password)
    return await login(client, email=email, password=password)


def auth(token: str) -> dict:
    """Return Authorization header dict for API requests."""
    return {"Authorization": f"Bearer {token}"}


async def get_user_id(client: AsyncClient, token: str) -> str:
    """Return the user_id for the given access token."""
    resp = await client.get("/api/v1/users/me", headers=auth(token))
    assert resp.status_code == 200
    return resp.json()["id"]


async def get_balance(client: AsyncClient, token: str, group_id: str, user_id: str) -> str:
    """Return the net_balance string for a user in a group."""
    resp = await client.get(f"/api/v1/groups/{group_id}/balances", headers=auth(token))
    assert resp.status_code == 200
    for b in resp.json()["balances"]:
        if b["user_id"] == user_id:
            return b["net_balance"]
    raise KeyError(f"user {user_id} not found in balances for group {group_id}")
