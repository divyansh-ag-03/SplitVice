"""
Integration tests for the settlements module.

Covers: create, list, detail, delete, balance integration,
pairwise debt validation, decimal precision, and auth.
"""

from datetime import date

from httpx import AsyncClient

TODAY = str(date.today())


# ── Helpers ───────────────────────────────────────────────────────────────────


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


async def get_user_id(client: AsyncClient, token: str) -> str:
    return (await client.get("/api/v1/users/me", headers=auth(token))).json()["id"]


async def create_group(client: AsyncClient, token: str, name: str = "Test Group") -> dict:
    resp = await client.post("/api/v1/groups", json={"name": name}, headers=auth(token))
    assert resp.status_code == 201
    return resp.json()


async def add_member(client: AsyncClient, admin_token: str, group_id: str, email: str) -> None:
    resp = await client.post(
        f"/api/v1/groups/{group_id}/members",
        json={"email": email},
        headers=auth(admin_token),
    )
    assert resp.status_code == 200


async def create_expense(
    client: AsyncClient,
    token: str,
    group_id: str,
    *,
    amount: str,
    payer_id: str,
    splits: list[dict],
) -> dict:
    resp = await client.post(
        f"/api/v1/groups/{group_id}/expenses",
        json={
            "description": "Expense",
            "amount": amount,
            "payer_id": payer_id,
            "expense_date": TODAY,
            "splits": splits,
        },
        headers=auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def create_settlement(
    client: AsyncClient,
    token: str,
    group_id: str,
    *,
    payer_id: str,
    payee_id: str,
    amount: str,
    description: str | None = None,
) -> dict:
    body = {
        "payer_id": payer_id,
        "payee_id": payee_id,
        "amount": amount,
        "settlement_date": TODAY,
    }
    if description is not None:
        body["description"] = description
    resp = await client.post(
        f"/api/v1/groups/{group_id}/settlements",
        json=body,
        headers=auth(token),
    )
    return resp


async def get_net_balance(client: AsyncClient, token: str, group_id: str, user_id: str) -> str:
    resp = await client.get(f"/api/v1/groups/{group_id}/balances", headers=auth(token))
    assert resp.status_code == 200
    for b in resp.json()["balances"]:
        if b["user_id"] == user_id:
            return b["net_balance"]
    raise KeyError(f"user {user_id} not in balances")


# ── Settlement creation ───────────────────────────────────────────────────────


async def test_create_settlement_success(client: AsyncClient):
    """Bob owes Alice $45 — Bob settles $20."""
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
        ],
    )

    resp = await create_settlement(
        client, token_b, group["id"],
        payer_id=bob_id,
        payee_id=alice_id,
        amount="20.00",
        description="Partial payment",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["payer_id"] == bob_id
    assert body["payee_id"] == alice_id
    assert body["amount"] == "20.0000"
    assert body["description"] == "Partial payment"
    assert body["creator_id"] == bob_id


async def test_create_settlement_same_payer_payee_rejected(client: AsyncClient):
    token = await register_and_login(client)
    user_id = await get_user_id(client, token)
    group = await create_group(client, token)

    resp = await create_settlement(
        client, token, group["id"],
        payer_id=user_id,
        payee_id=user_id,
        amount="10.00",
    )
    assert resp.status_code == 422


async def test_create_settlement_non_member_payer_rejected(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    # Bob is NOT added to the group

    resp = await create_settlement(
        client, token_a, group["id"],
        payer_id=bob_id,
        payee_id=alice_id,
        amount="10.00",
    )
    assert resp.status_code == 422
    assert "Payer" in resp.json()["detail"]


async def test_create_settlement_non_member_creator_rejected(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)

    group = await create_group(client, token_a)
    # Bob is not in the group

    resp = await create_settlement(
        client, token_b, group["id"],
        payer_id=alice_id,
        payee_id=alice_id,
        amount="10.00",
    )
    assert resp.status_code == 403


async def test_create_settlement_negative_amount_rejected(client: AsyncClient):
    token = await register_and_login(client)
    group = await create_group(client, token)
    user_id = await get_user_id(client, token)

    resp = await client.post(
        f"/api/v1/groups/{group['id']}/settlements",
        json={
            "payer_id": user_id,
            "payee_id": str(__import__("uuid").uuid4()),
            "amount": "-10.00",
            "settlement_date": TODAY,
        },
        headers=auth(token),
    )
    assert resp.status_code == 422


async def test_create_settlement_no_debt_rejected(client: AsyncClient):
    """Cannot settle when no debt exists between the two users."""
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")
    # No expenses — no debt

    resp = await create_settlement(
        client, token_a, group["id"],
        payer_id=alice_id,
        payee_id=bob_id,
        amount="10.00",
    )
    assert resp.status_code == 409
    assert "No debt" in resp.json()["detail"]


async def test_create_settlement_over_debt_rejected(client: AsyncClient):
    """Bob owes Alice $45 — cannot settle $80."""
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
        ],
    )

    resp = await create_settlement(
        client, token_b, group["id"],
        payer_id=bob_id,
        payee_id=alice_id,
        amount="80.00",
    )
    assert resp.status_code == 409
    assert "exceeds" in resp.json()["detail"]


async def test_create_settlement_reverse_direction_rejected(client: AsyncClient):
    """Alice is owed money — Alice cannot pay Bob (wrong direction)."""
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
        ],
    )

    # Alice tries to pay Bob — but Bob owes Alice, not the other way
    resp = await create_settlement(
        client, token_a, group["id"],
        payer_id=alice_id,
        payee_id=bob_id,
        amount="10.00",
    )
    assert resp.status_code == 409


async def test_create_settlement_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/groups/00000000-0000-0000-0000-000000000001/settlements",
        json={
            "payer_id": "00000000-0000-0000-0000-000000000002",
            "payee_id": "00000000-0000-0000-0000-000000000003",
            "amount": "10.00",
            "settlement_date": TODAY,
        },
    )
    assert resp.status_code == 401


# ── Balance integration ───────────────────────────────────────────────────────


async def test_settlement_reduces_debt(client: AsyncClient):
    """Bob owes Alice $45. Bob settles $20. Alice now +25, Bob now -25."""
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
        ],
    )

    # Before settlement
    assert await get_net_balance(client, token_a, group["id"], alice_id) == "45.0000"
    assert await get_net_balance(client, token_a, group["id"], bob_id) == "-45.0000"

    await create_settlement(
        client, token_b, group["id"],
        payer_id=bob_id,
        payee_id=alice_id,
        amount="20.00",
    )

    # After settlement
    assert await get_net_balance(client, token_a, group["id"], alice_id) == "25.0000"
    assert await get_net_balance(client, token_a, group["id"], bob_id) == "-25.0000"


async def test_full_settlement_zeroes_balance(client: AsyncClient):
    """Bob settles the full $45 — both balances reach zero."""
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
        ],
    )

    await create_settlement(
        client, token_b, group["id"],
        payer_id=bob_id,
        payee_id=alice_id,
        amount="45.00",
    )

    assert await get_net_balance(client, token_a, group["id"], alice_id) == "0.0000"
    assert await get_net_balance(client, token_a, group["id"], bob_id) == "0.0000"


async def test_multiple_settlements_accumulate(client: AsyncClient):
    """Two partial settlements of $15 each reduce $45 debt to $15."""
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
        ],
    )

    await create_settlement(
        client, token_b, group["id"],
        payer_id=bob_id, payee_id=alice_id, amount="15.00",
    )
    await create_settlement(
        client, token_b, group["id"],
        payer_id=bob_id, payee_id=alice_id, amount="15.00",
    )

    assert await get_net_balance(client, token_a, group["id"], alice_id) == "15.0000"
    assert await get_net_balance(client, token_a, group["id"], bob_id) == "-15.0000"


async def test_delete_settlement_restores_balance(client: AsyncClient):
    """
    End-to-end financial correctness test:
    1. Alice pays $100, split equally with Bob → Alice +50, Bob -50
    2. Bob settles $20 → Alice +30, Bob -30
    3. Delete settlement → Alice +50, Bob -50 (restored)
    """
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    await create_expense(
        client, token_a, group["id"],
        amount="100.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "50.00"},
            {"user_id": bob_id, "amount": "50.00"},
        ],
    )

    # Step 2: Bob settles $20
    s_resp = await create_settlement(
        client, token_b, group["id"],
        payer_id=bob_id, payee_id=alice_id, amount="20.00",
    )
    assert s_resp.status_code == 201
    settlement_id = s_resp.json()["id"]

    assert await get_net_balance(client, token_a, group["id"], alice_id) == "30.0000"
    assert await get_net_balance(client, token_a, group["id"], bob_id) == "-30.0000"

    # Step 3: Delete the settlement
    del_resp = await client.delete(
        f"/api/v1/settlements/{settlement_id}", headers=auth(token_b)
    )
    assert del_resp.status_code == 204

    # Balances restored
    assert await get_net_balance(client, token_a, group["id"], alice_id) == "50.0000"
    assert await get_net_balance(client, token_a, group["id"], bob_id) == "-50.0000"


# ── List settlements ──────────────────────────────────────────────────────────


async def test_list_settlements_member_can_list(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
        ],
    )
    await create_settlement(
        client, token_b, group["id"],
        payer_id=bob_id, payee_id=alice_id, amount="20.00",
    )

    resp = await client.get(
        f"/api/v1/groups/{group['id']}/settlements", headers=auth(token_a)
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["amount"] == "20.0000"


async def test_list_settlements_non_member_rejected(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    group = await create_group(client, token_a)

    resp = await client.get(
        f"/api/v1/groups/{group['id']}/settlements", headers=auth(token_b)
    )
    assert resp.status_code == 403


async def test_list_settlements_excludes_deleted(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
        ],
    )
    s_resp = await create_settlement(
        client, token_b, group["id"],
        payer_id=bob_id, payee_id=alice_id, amount="20.00",
    )
    settlement_id = s_resp.json()["id"]

    await client.delete(f"/api/v1/settlements/{settlement_id}", headers=auth(token_b))

    resp = await client.get(
        f"/api/v1/groups/{group['id']}/settlements", headers=auth(token_a)
    )
    assert resp.json() == []


# ── Settlement detail ─────────────────────────────────────────────────────────


async def test_get_settlement_detail_member_can_view(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
        ],
    )
    s_resp = await create_settlement(
        client, token_b, group["id"],
        payer_id=bob_id, payee_id=alice_id, amount="20.00",
    )
    settlement_id = s_resp.json()["id"]

    resp = await client.get(f"/api/v1/settlements/{settlement_id}", headers=auth(token_a))
    assert resp.status_code == 200
    body = resp.json()
    assert body["payer_name"] == "Bob"
    assert body["payee_name"] == "Alice"
    assert body["creator_name"] == "Bob"


async def test_get_settlement_detail_non_member_rejected(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
        ],
    )
    s_resp = await create_settlement(
        client, token_b, group["id"],
        payer_id=bob_id, payee_id=alice_id, amount="20.00",
    )
    settlement_id = s_resp.json()["id"]

    # Carol is not in the group
    token_c = await register_and_login(client, name="Carol", email="carol@example.com")
    resp = await client.get(f"/api/v1/settlements/{settlement_id}", headers=auth(token_c))
    assert resp.status_code == 403


# ── Delete settlement ─────────────────────────────────────────────────────────


async def test_creator_can_delete_settlement(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
        ],
    )
    s_resp = await create_settlement(
        client, token_b, group["id"],
        payer_id=bob_id, payee_id=alice_id, amount="20.00",
    )
    settlement_id = s_resp.json()["id"]

    resp = await client.delete(f"/api/v1/settlements/{settlement_id}", headers=auth(token_b))
    assert resp.status_code == 204


async def test_non_creator_cannot_delete_settlement(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
        ],
    )
    # Bob creates the settlement
    s_resp = await create_settlement(
        client, token_b, group["id"],
        payer_id=bob_id, payee_id=alice_id, amount="20.00",
    )
    settlement_id = s_resp.json()["id"]

    # Alice tries to delete it — she is not the creator
    resp = await client.delete(f"/api/v1/settlements/{settlement_id}", headers=auth(token_a))
    assert resp.status_code == 403


async def test_soft_delete_hides_settlement(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
        ],
    )
    s_resp = await create_settlement(
        client, token_b, group["id"],
        payer_id=bob_id, payee_id=alice_id, amount="20.00",
    )
    settlement_id = s_resp.json()["id"]

    await client.delete(f"/api/v1/settlements/{settlement_id}", headers=auth(token_b))

    # Detail endpoint returns 404 after soft delete
    resp = await client.get(f"/api/v1/settlements/{settlement_id}", headers=auth(token_a))
    assert resp.status_code == 404


# ── Decimal precision ─────────────────────────────────────────────────────────


async def test_settlement_decimal_precision(client: AsyncClient):
    """Settlement with 4 decimal places is stored and returned exactly."""
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    await create_expense(
        client, token_a, group["id"],
        amount="90.0000",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.0000"},
            {"user_id": bob_id, "amount": "45.0000"},
        ],
    )

    resp = await create_settlement(
        client, token_b, group["id"],
        payer_id=bob_id, payee_id=alice_id, amount="10.1234",
    )
    assert resp.status_code == 201
    assert resp.json()["amount"] == "10.1234"
