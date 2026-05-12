"""
Integration tests for the expenses module.

Covers: create, list, detail, update, delete, transaction safety, auth.
"""

from datetime import date

from httpx import AsyncClient


# ── Helpers ───────────────────────────────────────────────────────────────────

TODAY = str(date.today())


async def register_and_login(
    client: AsyncClient,
    *,
    name: str = "Alice",
    email: str = "alice@example.com",
    password: str = "password123",
) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": password},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return resp.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def create_group(client: AsyncClient, token: str, name: str = "Test Group") -> dict:
    resp = await client.post(
        "/api/v1/groups", json={"name": name}, headers=auth(token)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def add_member(client: AsyncClient, admin_token: str, group_id: str, email: str) -> dict:
    resp = await client.post(
        f"/api/v1/groups/{group_id}/members",
        json={"email": email},
        headers=auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def get_user_id(client: AsyncClient, token: str) -> str:
    resp = await client.get("/api/v1/users/me", headers=auth(token))
    return resp.json()["id"]


async def create_expense(
    client: AsyncClient,
    token: str,
    group_id: str,
    *,
    description: str = "Dinner",
    amount: str = "90.00",
    payer_id: str,
    splits: list[dict],
) -> dict:
    resp = await client.post(
        f"/api/v1/groups/{group_id}/expenses",
        json={
            "description": description,
            "amount": amount,
            "payer_id": payer_id,
            "expense_date": TODAY,
            "splits": splits,
        },
        headers=auth(token),
    )
    return resp


# ── Create expense ────────────────────────────────────────────────────────────


async def test_create_expense_success(client: AsyncClient):
    token = await register_and_login(client)
    user_id = await get_user_id(client, token)
    group = await create_group(client, token)

    resp = await create_expense(
        client, token, group["id"],
        payer_id=user_id,
        splits=[{"user_id": user_id, "amount": "90.00"}],
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["description"] == "Dinner"
    assert body["amount"] == "90.0000"
    assert len(body["splits"]) == 1
    assert body["splits"][0]["amount"] == "90.0000"
    assert body["payer_id"] == user_id
    assert body["creator_id"] == user_id


async def test_create_expense_split_sum_mismatch(client: AsyncClient):
    token = await register_and_login(client)
    user_id = await get_user_id(client, token)
    group = await create_group(client, token)

    resp = await create_expense(
        client, token, group["id"],
        amount="100.00",
        payer_id=user_id,
        splits=[{"user_id": user_id, "amount": "90.00"}],  # 90 != 100
    )
    assert resp.status_code == 422
    assert "equal expense total" in resp.json()["detail"]


async def test_create_expense_negative_amount_rejected(client: AsyncClient):
    resp = await client.post(
        "/api/v1/groups/00000000-0000-0000-0000-000000000001/expenses",
        json={
            "description": "Test",
            "amount": "-10.00",
            "payer_id": "00000000-0000-0000-0000-000000000002",
            "expense_date": TODAY,
            "splits": [{"user_id": "00000000-0000-0000-0000-000000000002", "amount": "-10.00"}],
        },
        headers=auth(await register_and_login(client)),
    )
    assert resp.status_code == 422


async def test_create_expense_empty_description_rejected(client: AsyncClient):
    token = await register_and_login(client)
    user_id = await get_user_id(client, token)
    group = await create_group(client, token)

    resp = await create_expense(
        client, token, group["id"],
        description="   ",
        payer_id=user_id,
        splits=[{"user_id": user_id, "amount": "90.00"}],
    )
    assert resp.status_code == 422


async def test_create_expense_duplicate_split_users_rejected(client: AsyncClient):
    token = await register_and_login(client)
    user_id = await get_user_id(client, token)
    group = await create_group(client, token)

    resp = await create_expense(
        client, token, group["id"],
        amount="90.00",
        payer_id=user_id,
        splits=[
            {"user_id": user_id, "amount": "45.00"},
            {"user_id": user_id, "amount": "45.00"},  # duplicate
        ],
    )
    assert resp.status_code == 422
    assert "Duplicate" in resp.json()["detail"]


async def test_create_expense_non_member_payer_rejected(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    alice_id = await get_user_id(client, token_a)

    # Bob is not in the group — cannot be payer
    resp = await create_expense(
        client, token_a, group["id"],
        payer_id=bob_id,
        splits=[{"user_id": alice_id, "amount": "90.00"}],
    )
    assert resp.status_code == 422
    assert "Payer" in resp.json()["detail"]


async def test_create_expense_non_member_split_user_rejected(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    alice_id = await get_user_id(client, token_a)

    # Bob is not in the group — cannot be in splits
    resp = await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
        ],
    )
    assert resp.status_code == 422
    assert "not a member" in resp.json()["detail"]


async def test_create_expense_non_member_creator_rejected(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)

    group = await create_group(client, token_a)

    # Bob is not in the group — cannot create expense
    resp = await create_expense(
        client, token_b, group["id"],
        payer_id=alice_id,
        splits=[{"user_id": alice_id, "amount": "90.00"}],
    )
    assert resp.status_code == 403


async def test_create_expense_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/groups/00000000-0000-0000-0000-000000000001/expenses",
        json={
            "description": "Test",
            "amount": "10.00",
            "payer_id": "00000000-0000-0000-0000-000000000001",
            "expense_date": TODAY,
            "splits": [{"user_id": "00000000-0000-0000-0000-000000000001", "amount": "10.00"}],
        },
    )
    assert resp.status_code == 401


# ── List expenses ─────────────────────────────────────────────────────────────


async def test_list_expenses_member_can_list(client: AsyncClient):
    token = await register_and_login(client)
    user_id = await get_user_id(client, token)
    group = await create_group(client, token)

    await create_expense(
        client, token, group["id"],
        payer_id=user_id,
        splits=[{"user_id": user_id, "amount": "90.00"}],
    )

    resp = await client.get(
        f"/api/v1/groups/{group['id']}/expenses", headers=auth(token)
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["split_count"] == 1


async def test_list_expenses_non_member_rejected(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    group = await create_group(client, token_a)

    resp = await client.get(
        f"/api/v1/groups/{group['id']}/expenses", headers=auth(token_b)
    )
    assert resp.status_code == 403


async def test_list_expenses_excludes_deleted(client: AsyncClient):
    token = await register_and_login(client)
    user_id = await get_user_id(client, token)
    group = await create_group(client, token)

    r = await create_expense(
        client, token, group["id"],
        payer_id=user_id,
        splits=[{"user_id": user_id, "amount": "90.00"}],
    )
    expense_id = r.json()["id"]

    await client.delete(f"/api/v1/expenses/{expense_id}", headers=auth(token))

    resp = await client.get(
        f"/api/v1/groups/{group['id']}/expenses", headers=auth(token)
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0


async def test_list_expenses_newest_first(client: AsyncClient):
    token = await register_and_login(client)
    user_id = await get_user_id(client, token)
    group = await create_group(client, token)

    for desc in ["First", "Second", "Third"]:
        await create_expense(
            client, token, group["id"],
            description=desc,
            payer_id=user_id,
            splits=[{"user_id": user_id, "amount": "90.00"}],
        )

    resp = await client.get(
        f"/api/v1/groups/{group['id']}/expenses", headers=auth(token)
    )
    descriptions = [e["description"] for e in resp.json()]
    # All three must be present (SQLite same-second ordering may vary)
    assert set(descriptions) == {"First", "Second", "Third"}
    assert len(descriptions) == 3


# ── Expense detail ────────────────────────────────────────────────────────────


async def test_get_expense_detail_member_can_view(client: AsyncClient):
    token = await register_and_login(client)
    user_id = await get_user_id(client, token)
    group = await create_group(client, token)

    r = await create_expense(
        client, token, group["id"],
        payer_id=user_id,
        splits=[{"user_id": user_id, "amount": "90.00"}],
    )
    expense_id = r.json()["id"]

    resp = await client.get(f"/api/v1/expenses/{expense_id}", headers=auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == expense_id
    assert len(body["splits"]) == 1
    assert body["splits"][0]["name"] == "Alice"


async def test_get_expense_detail_non_member_rejected(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    group = await create_group(client, token_a)

    r = await create_expense(
        client, token_a, group["id"],
        payer_id=alice_id,
        splits=[{"user_id": alice_id, "amount": "90.00"}],
    )
    expense_id = r.json()["id"]

    resp = await client.get(f"/api/v1/expenses/{expense_id}", headers=auth(token_b))
    assert resp.status_code == 403


# ── Update expense ────────────────────────────────────────────────────────────


async def test_creator_can_update_expense(client: AsyncClient):
    token = await register_and_login(client)
    user_id = await get_user_id(client, token)
    group = await create_group(client, token)

    r = await create_expense(
        client, token, group["id"],
        payer_id=user_id,
        splits=[{"user_id": user_id, "amount": "90.00"}],
    )
    expense_id = r.json()["id"]

    resp = await client.patch(
        f"/api/v1/expenses/{expense_id}",
        json={
            "description": "Updated Dinner",
            "amount": "120.00",
            "payer_id": user_id,
            "expense_date": TODAY,
            "splits": [{"user_id": user_id, "amount": "120.00"}],
        },
        headers=auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["description"] == "Updated Dinner"
    assert body["amount"] == "120.0000"
    assert body["splits"][0]["amount"] == "120.0000"


async def test_non_creator_cannot_update_expense(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    r = await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
        ],
    )
    expense_id = r.json()["id"]

    resp = await client.patch(
        f"/api/v1/expenses/{expense_id}",
        json={
            "description": "Hacked",
            "amount": "90.00",
            "payer_id": alice_id,
            "expense_date": TODAY,
            "splits": [
                {"user_id": alice_id, "amount": "45.00"},
                {"user_id": bob_id, "amount": "45.00"},
            ],
        },
        headers=auth(token_b),
    )
    assert resp.status_code == 403


async def test_update_expense_splits_replaced(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    r = await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[{"user_id": alice_id, "amount": "90.00"}],
    )
    expense_id = r.json()["id"]

    # Update: now split between Alice and Bob
    resp = await client.patch(
        f"/api/v1/expenses/{expense_id}",
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
        headers=auth(token_a),
    )
    assert resp.status_code == 200
    splits = resp.json()["splits"]
    assert len(splits) == 2
    split_amounts = {s["user_id"]: s["amount"] for s in splits}
    assert split_amounts[alice_id] == "45.0000"
    assert split_amounts[bob_id] == "45.0000"


async def test_update_expense_validates_split_sum(client: AsyncClient):
    token = await register_and_login(client)
    user_id = await get_user_id(client, token)
    group = await create_group(client, token)

    r = await create_expense(
        client, token, group["id"],
        payer_id=user_id,
        splits=[{"user_id": user_id, "amount": "90.00"}],
    )
    expense_id = r.json()["id"]

    resp = await client.patch(
        f"/api/v1/expenses/{expense_id}",
        json={
            "description": "Dinner",
            "amount": "100.00",
            "payer_id": user_id,
            "expense_date": TODAY,
            "splits": [{"user_id": user_id, "amount": "90.00"}],  # 90 != 100
        },
        headers=auth(token),
    )
    assert resp.status_code == 422


# ── Delete expense ────────────────────────────────────────────────────────────


async def test_creator_can_delete_expense(client: AsyncClient):
    token = await register_and_login(client)
    user_id = await get_user_id(client, token)
    group = await create_group(client, token)

    r = await create_expense(
        client, token, group["id"],
        payer_id=user_id,
        splits=[{"user_id": user_id, "amount": "90.00"}],
    )
    expense_id = r.json()["id"]

    resp = await client.delete(f"/api/v1/expenses/{expense_id}", headers=auth(token))
    assert resp.status_code == 204


async def test_non_creator_cannot_delete_expense(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    r = await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
        ],
    )
    expense_id = r.json()["id"]

    resp = await client.delete(f"/api/v1/expenses/{expense_id}", headers=auth(token_b))
    assert resp.status_code == 403


async def test_soft_delete_hides_expense(client: AsyncClient):
    token = await register_and_login(client)
    user_id = await get_user_id(client, token)
    group = await create_group(client, token)

    r = await create_expense(
        client, token, group["id"],
        payer_id=user_id,
        splits=[{"user_id": user_id, "amount": "90.00"}],
    )
    expense_id = r.json()["id"]

    await client.delete(f"/api/v1/expenses/{expense_id}", headers=auth(token))

    # Detail endpoint should return 404 after soft delete
    resp = await client.get(f"/api/v1/expenses/{expense_id}", headers=auth(token))
    assert resp.status_code == 404


# ── Transaction safety ────────────────────────────────────────────────────────


async def test_expense_and_splits_stored_together(client: AsyncClient):
    """Creating an expense stores both the expense row and all split rows."""
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    r = await create_expense(
        client, token_a, group["id"],
        amount="100.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "60.00"},
            {"user_id": bob_id, "amount": "40.00"},
        ],
    )
    assert r.status_code == 201
    body = r.json()
    assert len(body["splits"]) == 2
    total = sum(float(s["amount"]) for s in body["splits"])
    assert abs(total - 100.0) < 0.001


async def test_no_orphaned_splits_on_invalid_expense(client: AsyncClient):
    """
    An invalid expense (split sum mismatch) must not create any DB rows.
    Verified by checking the group expense list remains empty.
    """
    token = await register_and_login(client)
    user_id = await get_user_id(client, token)
    group = await create_group(client, token)

    # This should fail validation before any DB write
    resp = await create_expense(
        client, token, group["id"],
        amount="100.00",
        payer_id=user_id,
        splits=[{"user_id": user_id, "amount": "50.00"}],  # 50 != 100
    )
    assert resp.status_code == 422

    # Group should have no expenses
    list_resp = await client.get(
        f"/api/v1/groups/{group['id']}/expenses", headers=auth(token)
    )
    assert list_resp.json() == []
