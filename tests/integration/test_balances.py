"""
Integration tests for the balance computation module.

Covers: group balances, my balance, simplified debts, decimal precision,
leave/remove integration, and auth.
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
    description: str = "Expense",
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
    assert resp.status_code == 201, resp.text
    return resp.json()


async def get_balances(client: AsyncClient, token: str, group_id: str) -> dict:
    resp = await client.get(f"/api/v1/groups/{group_id}/balances", headers=auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


def balance_for(balances_response: dict, user_id: str) -> str:
    for b in balances_response["balances"]:
        if b["user_id"] == user_id:
            return b["net_balance"]
    raise KeyError(f"user {user_id} not in balances")


# ── Balance computation ───────────────────────────────────────────────────────


async def test_simple_two_user_expense(client: AsyncClient):
    """Alice pays $90, split equally: Alice +45, Bob -45."""
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

    data = await get_balances(client, token_a, group["id"])
    assert balance_for(data, alice_id) == "45.0000"
    assert balance_for(data, bob_id) == "-45.0000"


async def test_multi_user_split(client: AsyncClient):
    """Alice pays $120, split 3 ways: Alice +80, Bob -40, Carol -40."""
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    token_c = await register_and_login(client, name="Carol", email="carol@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)
    carol_id = await get_user_id(client, token_c)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")
    await add_member(client, token_a, group["id"], "carol@example.com")

    await create_expense(
        client, token_a, group["id"],
        amount="120.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "40.00"},
            {"user_id": bob_id, "amount": "40.00"},
            {"user_id": carol_id, "amount": "40.00"},
        ],
    )

    data = await get_balances(client, token_a, group["id"])
    assert balance_for(data, alice_id) == "80.0000"
    assert balance_for(data, bob_id) == "-40.0000"
    assert balance_for(data, carol_id) == "-40.0000"


async def test_uneven_split(client: AsyncClient):
    """Alice pays $100, Bob owes $70, Alice owes $30: Alice net +70, Bob net -70."""
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
            {"user_id": alice_id, "amount": "30.00"},
            {"user_id": bob_id, "amount": "70.00"},
        ],
    )

    data = await get_balances(client, token_a, group["id"])
    assert balance_for(data, alice_id) == "70.0000"
    assert balance_for(data, bob_id) == "-70.0000"


async def test_multiple_expenses(client: AsyncClient):
    """Two expenses: Alice pays $60 (Bob owes $30), Bob pays $40 (Alice owes $20).
    Alice net: 60 - 20 - 30 = +10. Bob net: 40 - 30 - 20 = -10."""
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    # Alice pays $60, split evenly
    await create_expense(
        client, token_a, group["id"],
        amount="60.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "30.00"},
            {"user_id": bob_id, "amount": "30.00"},
        ],
    )
    # Bob pays $40, split evenly
    await create_expense(
        client, token_b, group["id"],
        amount="40.00",
        payer_id=bob_id,
        splits=[
            {"user_id": alice_id, "amount": "20.00"},
            {"user_id": bob_id, "amount": "20.00"},
        ],
    )

    data = await get_balances(client, token_a, group["id"])
    # Alice: paid 60, owed 30+20=50 → net = 60-50 = +10
    assert balance_for(data, alice_id) == "10.0000"
    # Bob: paid 40, owed 30+20=50 → net = 40-50 = -10
    assert balance_for(data, bob_id) == "-10.0000"


async def test_deleted_expense_excluded(client: AsyncClient):
    """Deleting an expense removes it from balance computation."""
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    expense = await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
        ],
    )

    # Delete the expense
    await client.delete(f"/api/v1/expenses/{expense['id']}", headers=auth(token_a))

    data = await get_balances(client, token_a, group["id"])
    assert balance_for(data, alice_id) == "0.0000"
    assert balance_for(data, bob_id) == "0.0000"


# ── Net balance signs ─────────────────────────────────────────────────────────


async def test_zero_balance_member(client: AsyncClient):
    """A member with no expenses has zero balance."""
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    data = await get_balances(client, token_a, group["id"])
    assert balance_for(data, bob_id) == "0.0000"


# ── Simplified debts ──────────────────────────────────────────────────────────


async def test_simplified_debts_two_users(client: AsyncClient):
    """Bob owes Alice $45 → one simplified debt: Bob → Alice $45."""
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

    data = await get_balances(client, token_a, group["id"])
    debts = data["simplified_debts"]
    assert len(debts) == 1
    assert debts[0]["from_user_id"] == bob_id
    assert debts[0]["to_user_id"] == alice_id
    assert debts[0]["amount"] == "45.0000"


async def test_simplified_debts_three_users(client: AsyncClient):
    """
    Alice pays $120, split 3 ways ($40 each).
    Alice net +80, Bob net -40, Carol net -40.
    Simplified: Bob → Alice $40, Carol → Alice $40 (2 debts, not 3).
    """
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    token_c = await register_and_login(client, name="Carol", email="carol@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)
    carol_id = await get_user_id(client, token_c)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")
    await add_member(client, token_a, group["id"], "carol@example.com")

    await create_expense(
        client, token_a, group["id"],
        amount="120.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "40.00"},
            {"user_id": bob_id, "amount": "40.00"},
            {"user_id": carol_id, "amount": "40.00"},
        ],
    )

    data = await get_balances(client, token_a, group["id"])
    debts = data["simplified_debts"]
    assert len(debts) == 2
    # Both debts go to Alice
    assert all(d["to_user_id"] == alice_id for d in debts)
    # Debtors are Bob and Carol
    from_ids = {d["from_user_id"] for d in debts}
    assert from_ids == {bob_id, carol_id}
    # Each debt is $40
    assert all(d["amount"] == "40.0000" for d in debts)


async def test_no_debts_when_all_settled(client: AsyncClient):
    """When all balances are zero, simplified_debts is empty."""
    token = await register_and_login(client)
    group = await create_group(client, token)

    data = await get_balances(client, token, group["id"])
    assert data["simplified_debts"] == []


# ── My balance endpoint ───────────────────────────────────────────────────────


async def test_my_balance_breakdown(client: AsyncClient):
    """GET /balances/me returns correct breakdown for the current user."""
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
            {"user_id": alice_id, "amount": "40.00"},
            {"user_id": bob_id, "amount": "60.00"},
        ],
    )

    resp = await client.get(
        f"/api/v1/groups/{group['id']}/balances/me", headers=auth(token_a)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_paid"] == "100.0000"
    assert body["total_owed"] == "40.0000"
    assert body["net_balance"] == "60.0000"


async def test_my_balance_non_member_rejected(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    group = await create_group(client, token_a)

    resp = await client.get(
        f"/api/v1/groups/{group['id']}/balances/me", headers=auth(token_b)
    )
    assert resp.status_code == 403


# ── Group access ──────────────────────────────────────────────────────────────


async def test_balances_non_member_rejected(client: AsyncClient):
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    group = await create_group(client, token_a)

    resp = await client.get(
        f"/api/v1/groups/{group['id']}/balances", headers=auth(token_b)
    )
    assert resp.status_code == 403


async def test_balances_requires_auth(client: AsyncClient):
    token = await register_and_login(client)
    group = await create_group(client, token)

    resp = await client.get(f"/api/v1/groups/{group['id']}/balances")
    assert resp.status_code == 401


# ── Leave/remove integration ──────────────────────────────────────────────────


async def test_user_with_nonzero_balance_cannot_leave(client: AsyncClient):
    """Bob owes Alice money — Bob cannot leave the group."""
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

    resp = await client.post(
        f"/api/v1/groups/{group['id']}/leave", headers=auth(token_b)
    )
    assert resp.status_code == 409


async def test_admin_cannot_remove_member_with_nonzero_balance(client: AsyncClient):
    """Alice cannot remove Bob while Bob has an outstanding balance."""
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

    resp = await client.delete(
        f"/api/v1/groups/{group['id']}/members/{bob_id}", headers=auth(token_a)
    )
    assert resp.status_code == 409


async def test_settled_user_can_leave(client: AsyncClient):
    """After Bob's balance reaches zero, he can leave."""
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    group = await create_group(client, token_a)
    await add_member(client, token_a, group["id"], "bob@example.com")

    # Alice pays $90, Bob owes $45
    expense = await create_expense(
        client, token_a, group["id"],
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
        ],
    )

    # Delete the expense — Bob's balance returns to zero
    await client.delete(f"/api/v1/expenses/{expense['id']}", headers=auth(token_a))

    # Now Bob can leave
    resp = await client.post(
        f"/api/v1/groups/{group['id']}/leave", headers=auth(token_b)
    )
    assert resp.status_code == 204


# ── Decimal precision ─────────────────────────────────────────────────────────


async def test_decimal_precision_no_float_residue(client: AsyncClient):
    """Amounts with many decimal places are stored and returned exactly."""
    token = await register_and_login(client)
    user_id = await get_user_id(client, token)
    group = await create_group(client, token)

    await create_expense(
        client, token, group["id"],
        amount="33.3333",
        payer_id=user_id,
        splits=[{"user_id": user_id, "amount": "33.3333"}],
    )

    data = await get_balances(client, token, group["id"])
    # Payer paid 33.3333, owed 33.3333 → net = 0
    assert balance_for(data, user_id) == "0.0000"


async def test_no_negative_zero_in_output(client: AsyncClient):
    """A member with zero balance shows 0.0000, not -0.0000."""
    token = await register_and_login(client)
    user_id = await get_user_id(client, token)
    group = await create_group(client, token)

    data = await get_balances(client, token, group["id"])
    assert balance_for(data, user_id) == "0.0000"
    assert not balance_for(data, user_id).startswith("-")
