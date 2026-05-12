"""
End-to-end integration tests.

These tests exercise complete user journeys across all modules.
They are the most important tests in the suite — they verify that
the system works correctly as a whole, not just in isolation.

Test data uses named users (Alice, Bob, Charlie) with explicit
financial numbers so failures are immediately understandable.
"""

from decimal import Decimal
from datetime import date

from httpx import AsyncClient

from tests.helpers.auth import TODAY, auth, get_balance, get_user_id, register_and_login


# ── Shared setup helpers ──────────────────────────────────────────────────────


async def setup_group_with_three_members(client: AsyncClient) -> dict:
    """
    Register Alice, Bob, Charlie. Alice creates a group and adds both.
    Returns dict with tokens, user_ids, and group_id.
    """
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    token_c = await register_and_login(client, name="Charlie", email="charlie@example.com")

    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)
    charlie_id = await get_user_id(client, token_c)

    group_resp = await client.post(
        "/api/v1/groups", json={"name": "Dinner Group"}, headers=auth(token_a)
    )
    assert group_resp.status_code == 201
    group_id = group_resp.json()["id"]

    r = await client.post(
        f"/api/v1/groups/{group_id}/members",
        json={"email": "bob@example.com"},
        headers=auth(token_a),
    )
    assert r.status_code == 200

    r = await client.post(
        f"/api/v1/groups/{group_id}/members",
        json={"email": "charlie@example.com"},
        headers=auth(token_a),
    )
    assert r.status_code == 200

    return {
        "group_id": group_id,
        "token_a": token_a, "alice_id": alice_id,
        "token_b": token_b, "bob_id": bob_id,
        "token_c": token_c, "charlie_id": charlie_id,
    }


async def create_expense(
    client: AsyncClient,
    token: str,
    group_id: str,
    *,
    description: str,
    amount: str,
    payer_id: str,
    splits: list[dict],
) -> str:
    """Create an expense and return its id."""
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
    return resp.json()["id"]


async def create_settlement(
    client: AsyncClient,
    token: str,
    group_id: str,
    *,
    payer_id: str,
    payee_id: str,
    amount: str,
) -> str:
    """Create a settlement and return its id."""
    resp = await client.post(
        f"/api/v1/groups/{group_id}/settlements",
        json={
            "payer_id": payer_id,
            "payee_id": payee_id,
            "amount": amount,
            "settlement_date": TODAY,
        },
        headers=auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def assert_balance(actual: str, expected: str, label: str = "") -> None:
    """Assert two balance strings are equal with a readable message."""
    assert Decimal(actual) == Decimal(expected), (
        f"Balance mismatch{' for ' + label if label else ''}: "
        f"got {actual}, expected {expected}"
    )


def assert_balances_sum_to_zero(balances: list[dict]) -> None:
    """Critical invariant: all net balances in a group must sum to zero."""
    total = sum(Decimal(b["net_balance"]) for b in balances)
    assert total == Decimal("0.0000"), (
        f"Balances do not sum to zero: {total}. "
        f"Individual balances: {[(b['display_name'], b['net_balance']) for b in balances]}"
    )


# ── Core E2E flow ─────────────────────────────────────────────────────────────


async def test_core_financial_journey(client: AsyncClient):
    """
    Complete Alice/Bob/Charlie financial journey.

    Step 1: Alice pays $120 for dinner, split equally ($40 each)
            → Alice +80, Bob -40, Charlie -40

    Step 2: Bob settles $20 to Alice
            → Alice +60, Bob -20, Charlie -40

    Step 3: Charlie settles full $40 to Alice
            → Alice +20, Bob -20, Charlie 0

    Step 4: Bob settles remaining $20 to Alice
            → Alice 0, Bob 0, Charlie 0

    Step 5: Bob leaves group (zero balance)
    """
    ctx = await setup_group_with_three_members(client)
    group_id = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    token_b, bob_id = ctx["token_b"], ctx["bob_id"]
    token_c, charlie_id = ctx["token_c"], ctx["charlie_id"]

    # ── Step 1: Alice pays $120, split equally ────────────────────────────────
    await create_expense(
        client, token_a, group_id,
        description="Dinner",
        amount="120.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "40.00"},
            {"user_id": bob_id, "amount": "40.00"},
            {"user_id": charlie_id, "amount": "40.00"},
        ],
    )

    bal_resp = await client.get(f"/api/v1/groups/{group_id}/balances", headers=auth(token_a))
    balances = bal_resp.json()["balances"]
    assert_balances_sum_to_zero(balances)
    assert_balance(await get_balance(client, token_a, group_id, alice_id), "80.0000", "Alice after dinner")
    assert_balance(await get_balance(client, token_a, group_id, bob_id), "-40.0000", "Bob after dinner")
    assert_balance(await get_balance(client, token_a, group_id, charlie_id), "-40.0000", "Charlie after dinner")

    # Verify simplified debts: Bob → Alice $40, Charlie → Alice $40
    debts = bal_resp.json()["simplified_debts"]
    assert len(debts) == 2
    assert all(d["to_user_id"] == alice_id for d in debts)

    # ── Step 2: Bob settles $20 to Alice ─────────────────────────────────────
    await create_settlement(
        client, token_b, group_id,
        payer_id=bob_id, payee_id=alice_id, amount="20.00",
    )

    balances = (await client.get(f"/api/v1/groups/{group_id}/balances", headers=auth(token_a))).json()["balances"]
    assert_balances_sum_to_zero(balances)
    assert_balance(await get_balance(client, token_a, group_id, alice_id), "60.0000", "Alice after Bob partial")
    assert_balance(await get_balance(client, token_a, group_id, bob_id), "-20.0000", "Bob after partial")
    assert_balance(await get_balance(client, token_a, group_id, charlie_id), "-40.0000", "Charlie unchanged")

    # ── Step 3: Charlie settles full $40 to Alice ─────────────────────────────
    await create_settlement(
        client, token_c, group_id,
        payer_id=charlie_id, payee_id=alice_id, amount="40.00",
    )

    balances = (await client.get(f"/api/v1/groups/{group_id}/balances", headers=auth(token_a))).json()["balances"]
    assert_balances_sum_to_zero(balances)
    assert_balance(await get_balance(client, token_a, group_id, alice_id), "20.0000", "Alice after Charlie full")
    assert_balance(await get_balance(client, token_a, group_id, bob_id), "-20.0000", "Bob still owes")
    assert_balance(await get_balance(client, token_a, group_id, charlie_id), "0.0000", "Charlie settled")

    # ── Step 4: Bob settles remaining $20 ────────────────────────────────────
    await create_settlement(
        client, token_b, group_id,
        payer_id=bob_id, payee_id=alice_id, amount="20.00",
    )

    balances = (await client.get(f"/api/v1/groups/{group_id}/balances", headers=auth(token_a))).json()["balances"]
    assert_balances_sum_to_zero(balances)
    assert_balance(await get_balance(client, token_a, group_id, alice_id), "0.0000", "Alice fully settled")
    assert_balance(await get_balance(client, token_a, group_id, bob_id), "0.0000", "Bob fully settled")
    assert_balance(await get_balance(client, token_a, group_id, charlie_id), "0.0000", "Charlie fully settled")

    # No simplified debts when everyone is settled
    debts = (await client.get(f"/api/v1/groups/{group_id}/balances", headers=auth(token_a))).json()["simplified_debts"]
    assert debts == []

    # ── Step 5: Bob leaves (zero balance) ────────────────────────────────────
    leave_resp = await client.post(
        f"/api/v1/groups/{group_id}/leave", headers=auth(token_b)
    )
    assert leave_resp.status_code == 204

    # Bob no longer sees the group
    groups = (await client.get("/api/v1/groups", headers=auth(token_b))).json()
    assert all(g["id"] != group_id for g in groups)


# ── Settlement reversal ───────────────────────────────────────────────────────


async def test_settlement_reversal_restores_balances(client: AsyncClient):
    """
    Deleting a settlement must restore balances to their pre-settlement state.
    This verifies the dynamic balance computation is correct.
    """
    ctx = await setup_group_with_three_members(client)
    group_id = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    token_b, bob_id = ctx["token_b"], ctx["bob_id"]
    token_c, charlie_id = ctx["token_c"], ctx["charlie_id"]

    # Alice pays $90, Bob owes $45
    await create_expense(
        client, token_a, group_id,
        description="Lunch",
        amount="90.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
            
        ],
    )

    # Bob settles $30
    settlement_id = await create_settlement(
        client, token_b, group_id,
        payer_id=bob_id, payee_id=alice_id, amount="30.00",
    )

    assert_balance(await get_balance(client, token_a, group_id, alice_id), "15.0000", "Alice after partial settlement")
    assert_balance(await get_balance(client, token_a, group_id, bob_id), "-15.0000", "Bob after partial settlement")

    # Delete the settlement
    del_resp = await client.delete(f"/api/v1/settlements/{settlement_id}", headers=auth(token_b))
    assert del_resp.status_code == 204

    # Balances restored to pre-settlement state
    assert_balance(await get_balance(client, token_a, group_id, alice_id), "45.0000", "Alice restored")
    assert_balance(await get_balance(client, token_a, group_id, bob_id), "-45.0000", "Bob restored")

    # Invariant still holds
    balances = (await client.get(f"/api/v1/groups/{group_id}/balances", headers=auth(token_a))).json()["balances"]
    assert_balances_sum_to_zero(balances)


# ── Financial invariant: balances always sum to zero ─────────────────────────


async def test_balances_sum_to_zero_invariant(client: AsyncClient):
    """
    After any combination of expenses and settlements,
    the sum of all member net balances must equal zero.
    This is the fundamental accounting invariant.
    """
    ctx = await setup_group_with_three_members(client)
    group_id = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    token_b, bob_id = ctx["token_b"], ctx["bob_id"]
    token_c, charlie_id = ctx["token_c"], ctx["charlie_id"]

    def check_invariant():
        import asyncio
        # We can't await here, so we return a coroutine to be awaited by the caller
        return client.get(f"/api/v1/groups/{group_id}/balances", headers=auth(token_a))

    # After each operation, verify the invariant
    operations = [
        # Alice pays $100, split 3 ways
        lambda: create_expense(
            client, token_a, group_id,
            description="Groceries", amount="100.00", payer_id=alice_id,
            splits=[
                {"user_id": alice_id, "amount": "33.34"},
                {"user_id": bob_id, "amount": "33.33"},
                {"user_id": charlie_id, "amount": "33.33"},
            ],
        ),
        # Bob pays $60, split between Bob and Charlie
        lambda: create_expense(
            client, token_b, group_id,
            description="Taxi", amount="60.00", payer_id=bob_id,
            splits=[
                {"user_id": bob_id, "amount": "30.00"},
                {"user_id": charlie_id, "amount": "30.00"},
            ],
        ),
        # Charlie settles $20 to Alice
        lambda: create_settlement(
            client, token_c, group_id,
            payer_id=charlie_id, payee_id=alice_id, amount="20.00",
        ),
    ]

    for op in operations:
        await op()
        resp = await client.get(f"/api/v1/groups/{group_id}/balances", headers=auth(token_a))
        assert_balances_sum_to_zero(resp.json()["balances"])


# ── Soft delete consistency ───────────────────────────────────────────────────


async def test_deleted_expense_excluded_from_all_views(client: AsyncClient):
    """
    A soft-deleted expense must:
    - disappear from the expense list
    - be excluded from balance computation
    - return 404 on detail fetch
    """
    ctx = await setup_group_with_three_members(client)
    group_id = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    token_b, bob_id = ctx["token_b"], ctx["bob_id"]
    token_c, charlie_id = ctx["token_c"], ctx["charlie_id"]

    expense_id = await create_expense(
        client, token_a, group_id,
        description="Hotel", amount="120.00", payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "40.00"},
            {"user_id": bob_id, "amount": "40.00"},
            {"user_id": charlie_id, "amount": "40.00"},
        ],
    )

    # Verify expense exists and affects balances
    assert_balance(await get_balance(client, token_a, group_id, alice_id), "80.0000")

    # Delete the expense
    del_resp = await client.delete(f"/api/v1/expenses/{expense_id}", headers=auth(token_a))
    assert del_resp.status_code == 204

    # Expense list is empty
    list_resp = await client.get(f"/api/v1/groups/{group_id}/expenses", headers=auth(token_a))
    assert list_resp.json() == []

    # Balances are all zero
    assert_balance(await get_balance(client, token_a, group_id, alice_id), "0.0000")
    assert_balance(await get_balance(client, token_a, group_id, bob_id), "0.0000")

    # Detail returns 404
    detail_resp = await client.get(f"/api/v1/expenses/{expense_id}", headers=auth(token_a))
    assert detail_resp.status_code == 404


async def test_deleted_settlement_excluded_from_all_views(client: AsyncClient):
    """
    A soft-deleted settlement must:
    - disappear from the settlement list
    - be excluded from balance computation
    - return 404 on detail fetch
    """
    ctx = await setup_group_with_three_members(client)
    group_id = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    token_b, bob_id = ctx["token_b"], ctx["bob_id"]
    token_c, charlie_id = ctx["token_c"], ctx["charlie_id"]

    await create_expense(
        client, token_a, group_id,
        description="Dinner", amount="90.00", payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
            
        ],
    )

    settlement_id = await create_settlement(
        client, token_b, group_id,
        payer_id=bob_id, payee_id=alice_id, amount="45.00",
    )

    # Both at zero after settlement
    assert_balance(await get_balance(client, token_a, group_id, alice_id), "0.0000")

    # Delete settlement
    await client.delete(f"/api/v1/settlements/{settlement_id}", headers=auth(token_b))

    # Settlement list is empty
    list_resp = await client.get(f"/api/v1/groups/{group_id}/settlements", headers=auth(token_a))
    assert list_resp.json() == []

    # Balance restored
    assert_balance(await get_balance(client, token_a, group_id, alice_id), "45.0000")

    # Detail returns 404
    detail_resp = await client.get(f"/api/v1/settlements/{settlement_id}", headers=auth(token_a))
    assert detail_resp.status_code == 404


# ── Decimal precision ─────────────────────────────────────────────────────────


async def test_decimal_precision_preserved_end_to_end(client: AsyncClient):
    """
    Amounts with 4 decimal places must be stored and returned exactly.
    No float conversion anywhere in the pipeline.
    """
    ctx = await setup_group_with_three_members(client)
    group_id = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    token_b, bob_id = ctx["token_b"], ctx["bob_id"]
    token_c, charlie_id = ctx["token_c"], ctx["charlie_id"]

    # Use amounts with 4 decimal places
    expense_id = await create_expense(
        client, token_a, group_id,
        description="Precise split",
        amount="10.3333",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "3.4444"},
            {"user_id": bob_id, "amount": "3.4444"},
            {"user_id": charlie_id, "amount": "3.4445"},
        ],
    )

    # Verify stored amounts are exact
    detail = (await client.get(f"/api/v1/expenses/{expense_id}", headers=auth(token_a))).json()
    assert detail["amount"] == "10.3333"
    split_amounts = {s["user_id"]: s["amount"] for s in detail["splits"]}
    assert split_amounts[alice_id] == "3.4444"
    assert split_amounts[bob_id] == "3.4444"
    assert split_amounts[charlie_id] == "3.4445"

    # Verify balance is exact: Alice paid 10.3333, owes 3.4444 → net = 6.8889
    alice_balance = await get_balance(client, token_a, group_id, alice_id)
    assert Decimal(alice_balance) == Decimal("6.8889")

    # Invariant holds with decimal amounts
    balances = (await client.get(f"/api/v1/groups/{group_id}/balances", headers=auth(token_a))).json()["balances"]
    assert_balances_sum_to_zero(balances)

    # No negative zero in output
    for b in balances:
        assert not b["net_balance"].startswith("-0.0000"), f"Negative zero found: {b}"


# ── Negative / invalid scenarios ─────────────────────────────────────────────


async def test_cannot_settle_more_than_owed(client: AsyncClient):
    """Bob owes Alice $45. Bob cannot settle $100."""
    ctx = await setup_group_with_three_members(client)
    group_id = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    token_b, bob_id = ctx["token_b"], ctx["bob_id"]
    token_c, charlie_id = ctx["token_c"], ctx["charlie_id"]

    await create_expense(
        client, token_a, group_id,
        description="Dinner", amount="90.00", payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
            
        ],
    )

    resp = await client.post(
        f"/api/v1/groups/{group_id}/settlements",
        json={
            "payer_id": bob_id,
            "payee_id": alice_id,
            "amount": "100.00",
            "settlement_date": TODAY,
        },
        headers=auth(token_b),
    )
    assert resp.status_code == 409
    assert "exceeds" in resp.json()["detail"]

    # Balance unchanged
    assert_balance(await get_balance(client, token_a, group_id, bob_id), "-45.0000")


async def test_cannot_settle_in_wrong_direction(client: AsyncClient):
    """Alice is owed money. Alice cannot pay Bob (wrong direction)."""
    ctx = await setup_group_with_three_members(client)
    group_id = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    token_b, bob_id = ctx["token_b"], ctx["bob_id"]
    token_c, charlie_id = ctx["token_c"], ctx["charlie_id"]

    await create_expense(
        client, token_a, group_id,
        description="Dinner", amount="90.00", payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
            
        ],
    )

    # Alice tries to pay Bob — but Bob owes Alice
    resp = await client.post(
        f"/api/v1/groups/{group_id}/settlements",
        json={
            "payer_id": alice_id,
            "payee_id": bob_id,
            "amount": "10.00",
            "settlement_date": TODAY,
        },
        headers=auth(token_a),
    )
    assert resp.status_code == 409


async def test_cannot_settle_with_no_debt(client: AsyncClient):
    """No expenses exist — no debt to settle."""
    ctx = await setup_group_with_three_members(client)
    group_id = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    token_b, bob_id = ctx["token_b"], ctx["bob_id"]
    token_c, charlie_id = ctx["token_c"], ctx["charlie_id"]

    resp = await client.post(
        f"/api/v1/groups/{group_id}/settlements",
        json={
            "payer_id": bob_id,
            "payee_id": alice_id,
            "amount": "10.00",
            "settlement_date": TODAY,
        },
        headers=auth(token_b),
    )
    assert resp.status_code == 409
    assert "No debt" in resp.json()["detail"]


async def test_expense_split_sum_mismatch_rejected(client: AsyncClient):
    """Splits that don't sum to the expense total must be rejected atomically."""
    ctx = await setup_group_with_three_members(client)
    group_id = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    token_b, bob_id = ctx["token_b"], ctx["bob_id"]
    token_c, charlie_id = ctx["token_c"], ctx["charlie_id"]

    resp = await client.post(
        f"/api/v1/groups/{group_id}/expenses",
        json={
            "description": "Bad split",
            "amount": "100.00",
            "payer_id": alice_id,
            "expense_date": TODAY,
            "splits": [
                {"user_id": alice_id, "amount": "40.00"},
                {"user_id": bob_id, "amount": "40.00"},
                # Missing $20 — total is only $80
            ],
        },
        headers=auth(token_a),
    )
    assert resp.status_code == 422

    # No expense was created
    expenses = (await client.get(f"/api/v1/groups/{group_id}/expenses", headers=auth(token_a))).json()
    assert expenses == []

    # Balances are all zero (no orphaned data)
    balances = (await client.get(f"/api/v1/groups/{group_id}/balances", headers=auth(token_a))).json()["balances"]
    assert_balances_sum_to_zero(balances)
    for b in balances:
        assert Decimal(b["net_balance"]) == Decimal("0.0000")


async def test_member_with_nonzero_balance_cannot_leave(client: AsyncClient):
    """Bob owes Alice money — Bob cannot leave the group."""
    ctx = await setup_group_with_three_members(client)
    group_id = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    token_b, bob_id = ctx["token_b"], ctx["bob_id"]
    token_c, charlie_id = ctx["token_c"], ctx["charlie_id"]

    await create_expense(
        client, token_a, group_id,
        description="Dinner", amount="90.00", payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "45.00"},
            {"user_id": bob_id, "amount": "45.00"},
            
        ],
    )

    resp = await client.post(f"/api/v1/groups/{group_id}/leave", headers=auth(token_b))
    assert resp.status_code == 409

    # Bob is still in the group
    group = (await client.get(f"/api/v1/groups/{group_id}", headers=auth(token_a))).json()
    member_ids = [m["user_id"] for m in group["members"]]
    assert bob_id in member_ids


async def test_non_member_cannot_access_group_resources(client: AsyncClient):
    """A user not in the group cannot access expenses, balances, or settlements."""
    ctx = await setup_group_with_three_members(client)
    group_id = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]

    # Register an outsider
    token_x = await register_and_login(client, name="Xavier", email="xavier@example.com")

    # Cannot view group detail
    assert (await client.get(f"/api/v1/groups/{group_id}", headers=auth(token_x))).status_code == 403

    # Cannot view expenses
    assert (await client.get(f"/api/v1/groups/{group_id}/expenses", headers=auth(token_x))).status_code == 403

    # Cannot view balances
    assert (await client.get(f"/api/v1/groups/{group_id}/balances", headers=auth(token_x))).status_code == 403

    # Cannot view settlements
    assert (await client.get(f"/api/v1/groups/{group_id}/settlements", headers=auth(token_x))).status_code == 403


# ── Multiple expenses and payers ─────────────────────────────────────────────


async def test_multiple_expenses_multiple_payers(client: AsyncClient):
    """
    Realistic scenario: multiple expenses with different payers.
    Verify the final balances are correct and sum to zero.

    Alice pays $90 (split 3 ways: $30 each) → Alice +60, Bob -30, Charlie -30
    Bob pays $60 (split 2 ways: $30 each between Bob and Charlie) → Bob +30, Charlie -30
    Net: Alice +60, Bob 0, Charlie -60
    """
    ctx = await setup_group_with_three_members(client)
    group_id = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    token_b, bob_id = ctx["token_b"], ctx["bob_id"]
    token_c, charlie_id = ctx["token_c"], ctx["charlie_id"]

    await create_expense(
        client, token_a, group_id,
        description="Groceries", amount="90.00", payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "30.00"},
            {"user_id": bob_id, "amount": "30.00"},
            {"user_id": charlie_id, "amount": "30.00"},
        ],
    )

    await create_expense(
        client, token_b, group_id,
        description="Taxi", amount="60.00", payer_id=bob_id,
        splits=[
            {"user_id": bob_id, "amount": "30.00"},
            {"user_id": charlie_id, "amount": "30.00"},
        ],
    )

    balances = (await client.get(f"/api/v1/groups/{group_id}/balances", headers=auth(token_a))).json()["balances"]
    assert_balances_sum_to_zero(balances)

    assert_balance(await get_balance(client, token_a, group_id, alice_id), "60.0000", "Alice")
    assert_balance(await get_balance(client, token_a, group_id, bob_id), "0.0000", "Bob")
    assert_balance(await get_balance(client, token_a, group_id, charlie_id), "-60.0000", "Charlie")

    # Simplified debts: only Charlie → Alice $60
    debts = (await client.get(f"/api/v1/groups/{group_id}/balances", headers=auth(token_a))).json()["simplified_debts"]
    assert len(debts) == 1
    assert debts[0]["from_user_id"] == charlie_id
    assert debts[0]["to_user_id"] == alice_id
    assert Decimal(debts[0]["amount"]) == Decimal("60.0000")


# ── API infrastructure ────────────────────────────────────────────────────────


async def test_openapi_schema_is_served(client: AsyncClient):
    """OpenAPI schema must be accessible at /api/v1/openapi.json."""
    resp = await client.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["title"] == "SplitVice"
    assert "paths" in schema
    # Verify key endpoints are documented
    paths = schema["paths"]
    assert any("/auth/register" in p for p in paths)
    assert any("/groups" in p for p in paths)
    assert any("/expenses" in p for p in paths)
    assert any("/settlements" in p for p in paths)
    assert any("/balances" in p for p in paths)


async def test_health_endpoint(client: AsyncClient):
    """Health endpoint must return 200 with db=ok."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"


async def test_unauthenticated_api_requests_rejected(client: AsyncClient):
    """All protected API endpoints must return 401 without a token."""
    endpoints = [
        ("GET", "/api/v1/users/me"),
        ("GET", "/api/v1/groups"),
        ("POST", "/api/v1/groups"),
        ("GET", "/api/v1/groups/00000000-0000-0000-0000-000000000001"),
        ("GET", "/api/v1/groups/00000000-0000-0000-0000-000000000001/expenses"),
        ("GET", "/api/v1/groups/00000000-0000-0000-0000-000000000001/balances"),
        ("GET", "/api/v1/groups/00000000-0000-0000-0000-000000000001/settlements"),
    ]
    for method, path in endpoints:
        resp = await client.request(method, path)
        assert resp.status_code == 401, f"{method} {path} should return 401, got {resp.status_code}"


async def test_invalid_jwt_rejected(client: AsyncClient):
    """A tampered JWT must be rejected with 401."""
    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.tampered.signature"},
    )
    assert resp.status_code == 401


async def test_full_flow_register_to_settled(client: AsyncClient):
    """
    Condensed full-flow smoke test:
    register → login → create group → add member → create expense →
    check balances → settle → verify zero → leave group
    """
    # Setup
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob", email="bob@example.com")
    alice_id = await get_user_id(client, token_a)
    bob_id = await get_user_id(client, token_b)

    # Create group
    group = (await client.post("/api/v1/groups", json={"name": "Test"}, headers=auth(token_a))).json()
    group_id = group["id"]
    assert group["current_user_role"] == "admin"

    # Add Bob
    await client.post(
        f"/api/v1/groups/{group_id}/members",
        json={"email": "bob@example.com"},
        headers=auth(token_a),
    )

    # Alice pays $100, Bob owes $50
    expense_id = await create_expense(
        client, token_a, group_id,
        description="Dinner", amount="100.00", payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "50.00"},
            {"user_id": bob_id, "amount": "50.00"},
        ],
    )

    # Verify balances
    assert_balance(await get_balance(client, token_a, group_id, alice_id), "50.0000")
    assert_balance(await get_balance(client, token_a, group_id, bob_id), "-50.0000")

    # Bob settles $50
    await create_settlement(
        client, token_b, group_id,
        payer_id=bob_id, payee_id=alice_id, amount="50.00",
    )

    # Both at zero
    assert_balance(await get_balance(client, token_a, group_id, alice_id), "0.0000")
    assert_balance(await get_balance(client, token_a, group_id, bob_id), "0.0000")

    # Bob leaves
    assert (await client.post(f"/api/v1/groups/{group_id}/leave", headers=auth(token_b))).status_code == 204
