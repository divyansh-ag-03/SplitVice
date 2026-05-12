"""
Explicit tests for participant-aware balance computation.

The core invariant: a user only owes money for expenses they participated in.
Participation is determined EXCLUSIVELY by expense_splits rows.
Group membership does NOT imply participation in every expense.

These tests verify the exact scenario from the bug report:
  Group: A, B, C, D
  Expense 1: A pays 400, split A=100 B=100 C=100 D=100
  Expense 2: B pays 300, split B=100 C=100 D=100  (A NOT included)
  Expected: A=+300, B=+100, C=-200, D=-200
"""

from datetime import date
from decimal import Decimal

from httpx import AsyncClient

from tests.helpers.auth import TODAY, auth, get_balance, get_user_id, register_and_login


def assert_balance(actual: str, expected: str, label: str = "") -> None:
    assert Decimal(actual) == Decimal(expected), (
        f"Balance mismatch{' for ' + label if label else ''}: "
        f"got {actual}, expected {expected}"
    )


def assert_sum_zero(balances: list[dict]) -> None:
    total = sum(Decimal(b["net_balance"]) for b in balances)
    assert total == Decimal("0.0000"), (
        f"Balances do not sum to zero: {total}. "
        f"Values: {[(b['display_name'], b['net_balance']) for b in balances]}"
    )


async def setup_four_member_group(client: AsyncClient) -> dict:
    """Register A, B, C, D. A creates group and adds B, C, D."""
    token_a = await register_and_login(client, name="Alice", email="alice@example.com")
    token_b = await register_and_login(client, name="Bob",   email="bob@example.com")
    token_c = await register_and_login(client, name="Carol", email="carol@example.com")
    token_d = await register_and_login(client, name="Dave",  email="dave@example.com")

    alice_id = await get_user_id(client, token_a)
    bob_id   = await get_user_id(client, token_b)
    carol_id = await get_user_id(client, token_c)
    dave_id  = await get_user_id(client, token_d)

    group = (await client.post(
        "/api/v1/groups", json={"name": "Test Group"}, headers=auth(token_a)
    )).json()
    group_id = group["id"]

    for email in ["bob@example.com", "carol@example.com", "dave@example.com"]:
        r = await client.post(
            f"/api/v1/groups/{group_id}/members",
            json={"email": email}, headers=auth(token_a)
        )
        assert r.status_code == 200

    return {
        "group_id": group_id,
        "token_a": token_a, "alice_id": alice_id,
        "token_b": token_b, "bob_id": bob_id,
        "token_c": token_c, "carol_id": carol_id,
        "token_d": token_d, "dave_id": dave_id,
    }


async def create_expense(client, token, group_id, *, description, amount, payer_id, splits):
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


# ── Core scenario from the bug report ────────────────────────────────────────


async def test_partial_participation_core_scenario(client: AsyncClient):
    """
    THE critical test.

    Expense 1: A pays 400, split A=100 B=100 C=100 D=100
    Expense 2: B pays 300, split B=100 C=100 D=100  (A NOT included)

    Expected final balances:
      A: paid 400, owed 100 → net = +300
      B: paid 300, owed 100 → net = +200, but also owes 100 from Exp1 → net = +100
      C: paid 0,   owed 100+100=200 → net = -200
      D: paid 0,   owed 100+100=200 → net = -200

    A must be completely unaffected by Expense 2.
    """
    ctx = await setup_four_member_group(client)
    gid = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    token_b, bob_id   = ctx["token_b"], ctx["bob_id"]
    carol_id = ctx["carol_id"]
    dave_id  = ctx["dave_id"]

    # Expense 1: A pays 400, all four split equally
    await create_expense(
        client, token_a, gid,
        description="Expense 1",
        amount="400.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "100.00"},
            {"user_id": bob_id,   "amount": "100.00"},
            {"user_id": carol_id, "amount": "100.00"},
            {"user_id": dave_id,  "amount": "100.00"},
        ],
    )

    # Expense 2: B pays 300, only B, C, D split — A NOT included
    await create_expense(
        client, token_b, gid,
        description="Expense 2",
        amount="300.00",
        payer_id=bob_id,
        splits=[
            {"user_id": bob_id,   "amount": "100.00"},
            {"user_id": carol_id, "amount": "100.00"},
            {"user_id": dave_id,  "amount": "100.00"},
        ],
    )

    resp = await client.get(f"/api/v1/groups/{gid}/balances", headers=auth(token_a))
    assert resp.status_code == 200
    balances = resp.json()["balances"]

    assert_sum_zero(balances)
    assert_balance(await get_balance(client, token_a, gid, alice_id), "300.0000", "Alice")
    assert_balance(await get_balance(client, token_a, gid, bob_id),   "100.0000", "Bob")
    assert_balance(await get_balance(client, token_a, gid, carol_id), "-200.0000", "Carol")
    assert_balance(await get_balance(client, token_a, gid, dave_id),  "-200.0000", "Dave")


async def test_alice_unaffected_by_expense_she_did_not_join(client: AsyncClient):
    """
    Explicit check: Alice's balance must not change when an expense
    is created that does not include her in the splits.
    """
    ctx = await setup_four_member_group(client)
    gid = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    token_b, bob_id   = ctx["token_b"], ctx["bob_id"]
    carol_id = ctx["carol_id"]
    dave_id  = ctx["dave_id"]

    # Alice's balance before any expenses
    assert_balance(await get_balance(client, token_a, gid, alice_id), "0.0000", "Alice before")

    # Bob pays, splits only among B, C, D
    await create_expense(
        client, token_b, gid,
        description="Bob's expense",
        amount="90.00",
        payer_id=bob_id,
        splits=[
            {"user_id": bob_id,   "amount": "30.00"},
            {"user_id": carol_id, "amount": "30.00"},
            {"user_id": dave_id,  "amount": "30.00"},
        ],
    )

    # Alice's balance must still be zero
    assert_balance(await get_balance(client, token_a, gid, alice_id), "0.0000", "Alice after")

    balances = (await client.get(f"/api/v1/groups/{gid}/balances", headers=auth(token_a))).json()["balances"]
    assert_sum_zero(balances)


# ── Payer excluded from split ─────────────────────────────────────────────────


async def test_payer_excluded_from_split(client: AsyncClient):
    """
    A pays 120 but is NOT in the splits (pays entirely for others).
    B, C, D each owe 40.
    A net = +120, B = -40, C = -40, D = -40.
    """
    ctx = await setup_four_member_group(client)
    gid = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    bob_id   = ctx["bob_id"]
    carol_id = ctx["carol_id"]
    dave_id  = ctx["dave_id"]

    await create_expense(
        client, token_a, gid,
        description="A pays for others",
        amount="120.00",
        payer_id=alice_id,
        splits=[
            {"user_id": bob_id,   "amount": "40.00"},
            {"user_id": carol_id, "amount": "40.00"},
            {"user_id": dave_id,  "amount": "40.00"},
        ],
    )

    balances = (await client.get(f"/api/v1/groups/{gid}/balances", headers=auth(token_a))).json()["balances"]
    assert_sum_zero(balances)
    assert_balance(await get_balance(client, token_a, gid, alice_id), "120.0000", "Alice")
    assert_balance(await get_balance(client, token_a, gid, bob_id),   "-40.0000", "Bob")
    assert_balance(await get_balance(client, token_a, gid, carol_id), "-40.0000", "Carol")
    assert_balance(await get_balance(client, token_a, gid, dave_id),  "-40.0000", "Dave")


# ── Two-member expense inside larger group ────────────────────────────────────


async def test_two_member_expense_in_four_member_group(client: AsyncClient):
    """
    Only A and B are involved in an expense. C and D must be unaffected.
    A pays 100, B owes 50, A owes 50.
    Net: A=+50, B=-50, C=0, D=0.
    """
    ctx = await setup_four_member_group(client)
    gid = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    bob_id   = ctx["bob_id"]
    carol_id = ctx["carol_id"]
    dave_id  = ctx["dave_id"]

    await create_expense(
        client, token_a, gid,
        description="A and B only",
        amount="100.00",
        payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "50.00"},
            {"user_id": bob_id,   "amount": "50.00"},
        ],
    )

    balances = (await client.get(f"/api/v1/groups/{gid}/balances", headers=auth(token_a))).json()["balances"]
    assert_sum_zero(balances)
    assert_balance(await get_balance(client, token_a, gid, alice_id), "50.0000",  "Alice")
    assert_balance(await get_balance(client, token_a, gid, bob_id),   "-50.0000", "Bob")
    assert_balance(await get_balance(client, token_a, gid, carol_id), "0.0000",   "Carol")
    assert_balance(await get_balance(client, token_a, gid, dave_id),  "0.0000",   "Dave")


# ── Multiple partial-participation expenses ───────────────────────────────────


async def test_multiple_partial_participation_expenses(client: AsyncClient):
    """
    Expense 1: A pays 200, split A=100 B=100
    Expense 2: C pays 150, split C=50 D=100
    Expense 3: B pays 90,  split A=30 B=30 C=30

    Manual calculation:
      A: paid=200, owed=100+30=130 → net=+70
      B: paid=90,  owed=100+30=130 → net=-40
      C: paid=150, owed=50+30=80   → net=+70
      D: paid=0,   owed=100        → net=-100

    Sum: 70 - 40 + 70 - 100 = 0 ✓
    """
    ctx = await setup_four_member_group(client)
    gid = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    token_b, bob_id   = ctx["token_b"], ctx["bob_id"]
    token_c, carol_id = ctx["token_c"], ctx["carol_id"]
    dave_id  = ctx["dave_id"]

    await create_expense(
        client, token_a, gid,
        description="Exp1", amount="200.00", payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "100.00"},
            {"user_id": bob_id,   "amount": "100.00"},
        ],
    )
    await create_expense(
        client, token_c, gid,
        description="Exp2", amount="150.00", payer_id=carol_id,
        splits=[
            {"user_id": carol_id, "amount": "50.00"},
            {"user_id": dave_id,  "amount": "100.00"},
        ],
    )
    await create_expense(
        client, token_b, gid,
        description="Exp3", amount="90.00", payer_id=bob_id,
        splits=[
            {"user_id": alice_id, "amount": "30.00"},
            {"user_id": bob_id,   "amount": "30.00"},
            {"user_id": carol_id, "amount": "30.00"},
        ],
    )

    balances = (await client.get(f"/api/v1/groups/{gid}/balances", headers=auth(token_a))).json()["balances"]
    assert_sum_zero(balances)
    assert_balance(await get_balance(client, token_a, gid, alice_id), "70.0000",   "Alice")
    assert_balance(await get_balance(client, token_a, gid, bob_id),   "-40.0000",  "Bob")
    assert_balance(await get_balance(client, token_a, gid, carol_id), "70.0000",   "Carol")
    assert_balance(await get_balance(client, token_a, gid, dave_id),  "-100.0000", "Dave")


# ── Settlement after partial participation ────────────────────────────────────


async def test_settlement_after_partial_participation(client: AsyncClient):
    """
    After the core scenario (A=+300, B=+100, C=-200, D=-200),
    C settles 100 to A.
    Expected: A=+200, B=+100, C=-100, D=-200.
    """
    ctx = await setup_four_member_group(client)
    gid = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    token_b, bob_id   = ctx["token_b"], ctx["bob_id"]
    token_c, carol_id = ctx["token_c"], ctx["carol_id"]
    dave_id  = ctx["dave_id"]

    await create_expense(
        client, token_a, gid,
        description="Expense 1", amount="400.00", payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "100.00"},
            {"user_id": bob_id,   "amount": "100.00"},
            {"user_id": carol_id, "amount": "100.00"},
            {"user_id": dave_id,  "amount": "100.00"},
        ],
    )
    await create_expense(
        client, token_b, gid,
        description="Expense 2", amount="300.00", payer_id=bob_id,
        splits=[
            {"user_id": bob_id,   "amount": "100.00"},
            {"user_id": carol_id, "amount": "100.00"},
            {"user_id": dave_id,  "amount": "100.00"},
        ],
    )

    # C settles 100 to A
    resp = await client.post(
        f"/api/v1/groups/{gid}/settlements",
        json={
            "payer_id": carol_id,
            "payee_id": alice_id,
            "amount": "100.00",
            "settlement_date": TODAY,
        },
        headers=auth(token_c),
    )
    assert resp.status_code == 201

    balances = (await client.get(f"/api/v1/groups/{gid}/balances", headers=auth(token_a))).json()["balances"]
    assert_sum_zero(balances)
    assert_balance(await get_balance(client, token_a, gid, alice_id), "200.0000",  "Alice")
    assert_balance(await get_balance(client, token_a, gid, bob_id),   "100.0000",  "Bob")
    assert_balance(await get_balance(client, token_a, gid, carol_id), "-100.0000", "Carol")
    assert_balance(await get_balance(client, token_a, gid, dave_id),  "-200.0000", "Dave")


# ── Deleted expense recalculation ─────────────────────────────────────────────


async def test_deleted_expense_recalculation_with_partial_participation(client: AsyncClient):
    """
    After core scenario, delete Expense 2.
    Expected: A=+300, B=-100, C=-100, D=-100 (only Expense 1 remains).
    """
    ctx = await setup_four_member_group(client)
    gid = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    token_b, bob_id   = ctx["token_b"], ctx["bob_id"]
    carol_id = ctx["carol_id"]
    dave_id  = ctx["dave_id"]

    await create_expense(
        client, token_a, gid,
        description="Expense 1", amount="400.00", payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "100.00"},
            {"user_id": bob_id,   "amount": "100.00"},
            {"user_id": carol_id, "amount": "100.00"},
            {"user_id": dave_id,  "amount": "100.00"},
        ],
    )
    exp2_id = await create_expense(
        client, token_b, gid,
        description="Expense 2", amount="300.00", payer_id=bob_id,
        splits=[
            {"user_id": bob_id,   "amount": "100.00"},
            {"user_id": carol_id, "amount": "100.00"},
            {"user_id": dave_id,  "amount": "100.00"},
        ],
    )

    # Delete Expense 2
    del_resp = await client.delete(f"/api/v1/expenses/{exp2_id}", headers=auth(token_b))
    assert del_resp.status_code == 204

    balances = (await client.get(f"/api/v1/groups/{gid}/balances", headers=auth(token_a))).json()["balances"]
    assert_sum_zero(balances)
    assert_balance(await get_balance(client, token_a, gid, alice_id), "300.0000",  "Alice")
    assert_balance(await get_balance(client, token_a, gid, bob_id),   "-100.0000", "Bob")
    assert_balance(await get_balance(client, token_a, gid, carol_id), "-100.0000", "Carol")
    assert_balance(await get_balance(client, token_a, gid, dave_id),  "-100.0000", "Dave")


# ── Debt simplification with partial participation ────────────────────────────


async def test_debt_simplification_partial_participation(client: AsyncClient):
    """
    After core scenario (A=+300, B=+100, C=-200, D=-200):
    Simplified debts should be:
      C → A 200 (or C → A 100 + C → B 100, depending on algorithm)
      D → A 100 + D → B 100 (or D → A 200)

    The key invariant: applying all simplified debts zeroes all balances.
    Also: A must appear only as a creditor (to_user), never as a debtor.
    """
    ctx = await setup_four_member_group(client)
    gid = ctx["group_id"]
    token_a, alice_id = ctx["token_a"], ctx["alice_id"]
    token_b, bob_id   = ctx["token_b"], ctx["bob_id"]
    carol_id = ctx["carol_id"]
    dave_id  = ctx["dave_id"]

    await create_expense(
        client, token_a, gid,
        description="Expense 1", amount="400.00", payer_id=alice_id,
        splits=[
            {"user_id": alice_id, "amount": "100.00"},
            {"user_id": bob_id,   "amount": "100.00"},
            {"user_id": carol_id, "amount": "100.00"},
            {"user_id": dave_id,  "amount": "100.00"},
        ],
    )
    await create_expense(
        client, token_b, gid,
        description="Expense 2", amount="300.00", payer_id=bob_id,
        splits=[
            {"user_id": bob_id,   "amount": "100.00"},
            {"user_id": carol_id, "amount": "100.00"},
            {"user_id": dave_id,  "amount": "100.00"},
        ],
    )

    resp = await client.get(f"/api/v1/groups/{gid}/balances", headers=auth(token_a))
    data = resp.json()
    balances = data["balances"]
    debts = data["simplified_debts"]

    assert_sum_zero(balances)

    # Alice and Bob are creditors — they must never appear as from_user
    creditor_ids = {str(alice_id), str(bob_id)}
    for debt in debts:
        assert debt["from_user_id"] not in creditor_ids, (
            f"Creditor {debt['from_user_id']} incorrectly appears as debtor in: {debt}"
        )

    # Applying all debts must zero all balances
    net = {b["user_id"]: Decimal(b["net_balance"]) for b in balances}
    for debt in debts:
        net[debt["from_user_id"]] += Decimal(debt["amount"])
        net[debt["to_user_id"]]   -= Decimal(debt["amount"])
    for uid, bal in net.items():
        from app.services.balance_service import _normalize
        assert _normalize(bal) == Decimal("0.0000"), (
            f"After applying simplified debts, {uid} still has balance {bal}"
        )
