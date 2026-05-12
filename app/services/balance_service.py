"""
Balance service — computes net balances and simplified debts for a group.

Always derives from source-of-truth tables (expenses, splits, settlements).
Never stores computed balances. Never uses float.

Balance formula per member:
    net = total_paid - total_owed - settlements_paid + settlements_received

Positive net  → member is owed money (creditor)
Negative net  → member owes money (debtor)
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.repositories import balance_repository as balance_repo
from app.repositories import group_repository as group_repo
from app.schemas.balances import (
    GroupBalanceResponse,
    MemberBalance,
    MyBalanceResponse,
    SimplifiedDebt,
)

# Canonical zero — avoids -0.0000 in output
ZERO = Decimal("0.0000")
PRECISION = Decimal("0.0001")


def _normalize(value: Decimal) -> Decimal:
    """Quantize to 4 decimal places and eliminate negative zero."""
    result = value.quantize(PRECISION)
    return ZERO if result == ZERO else result


def _compute_net_balances(
    member_ids: list[UUID],
    paid: dict[UUID, Decimal],
    owed: dict[UUID, Decimal],
    settlements_paid: dict[UUID, Decimal],
    settlements_received: dict[UUID, Decimal],
) -> dict[UUID, Decimal]:
    """
    Compute net balance for each member.

    net = paid - owed + settlements_paid - settlements_received

    Explanation:
    - paid: money the member put in (increases their credit)
    - owed: money the member owes via splits (decreases their credit)
    - settlements_paid: money the member paid out to settle debts
      (decreases their balance — they are paying off what they owe)
    - settlements_received: money the member received as settlement
      (decreases their balance — they have been paid back)

    Example: Alice paid $90, owes $45 split, Bob pays Alice $20:
      Alice net = 90 - 45 + 0 - 20 = +25  ✓
      Bob net   =  0 - 45 + 20 - 0  = -25  ✓

    All missing keys default to zero.
    """
    balances: dict[UUID, Decimal] = {}
    for uid in member_ids:
        net = (
            paid.get(uid, ZERO)
            - owed.get(uid, ZERO)
            + settlements_paid.get(uid, ZERO)
            - settlements_received.get(uid, ZERO)
        )
        balances[uid] = _normalize(net)
    return balances


def _simplify_debts(
    balances: dict[UUID, Decimal],
    names: dict[UUID, str],
) -> list[SimplifiedDebt]:
    """
    Reduce a set of net balances to a minimal list of directional payments.

    Algorithm (greedy debtor-creditor matching):
    1. Split members into creditors (net > 0) and debtors (net < 0).
    2. Sort both lists by absolute value descending for deterministic output.
    3. Repeatedly match the largest debtor with the largest creditor:
       - Create a debt for min(|debtor|, creditor).
       - Reduce both balances by that amount.
       - Remove any member whose balance reaches zero.
    4. Repeat until all balances are zero.

    This produces at most N-1 transactions for N members and is easy to audit.
    """
    # Work with mutable copies, skip zero balances
    creditors: list[list] = [
        [uid, bal] for uid, bal in balances.items() if bal > ZERO
    ]
    debtors: list[list] = [
        [uid, -bal] for uid, bal in balances.items() if bal < ZERO
    ]

    # Sort by amount descending for deterministic output
    creditors.sort(key=lambda x: x[1], reverse=True)
    debtors.sort(key=lambda x: x[1], reverse=True)

    debts: list[SimplifiedDebt] = []

    ci = 0  # creditor index
    di = 0  # debtor index

    while ci < len(creditors) and di < len(debtors):
        creditor_id, credit = creditors[ci]
        debtor_id, debt = debtors[di]

        amount = min(credit, debt)
        amount = _normalize(amount)

        if amount > ZERO:
            debts.append(
                SimplifiedDebt(
                    from_user_id=debtor_id,
                    from_name=names.get(debtor_id, "Unknown"),
                    to_user_id=creditor_id,
                    to_name=names.get(creditor_id, "Unknown"),
                    amount=amount,
                )
            )

        creditors[ci][1] = _normalize(credit - amount)
        debtors[di][1] = _normalize(debt - amount)

        if creditors[ci][1] == ZERO:
            ci += 1
        if debtors[di][1] == ZERO:
            di += 1

    return debts


async def _load_group_balance_data(db: AsyncSession, group_id: UUID):
    """Fetch all aggregate data needed for balance computation."""
    member_ids = await balance_repo.get_member_user_ids(db, group_id)
    names = await balance_repo.get_user_names(db, member_ids)
    paid = await balance_repo.get_paid_totals(db, group_id)
    owed = await balance_repo.get_owed_totals(db, group_id)
    s_paid = await balance_repo.get_settlement_paid_totals(db, group_id)
    s_received = await balance_repo.get_settlement_received_totals(db, group_id)
    return member_ids, names, paid, owed, s_paid, s_received


# ── Public service functions ──────────────────────────────────────────────────


async def get_group_balances(
    db: AsyncSession,
    group_id: UUID,
    current_user_id: UUID,
) -> GroupBalanceResponse:
    """
    Return net balances and simplified debts for all group members.
    Only accessible to group members.
    """
    group = await group_repo.get_group_by_id(db, group_id)
    if group is None:
        raise NotFoundError("Group not found")

    membership = await group_repo.get_membership(db, group_id, current_user_id)
    if membership is None:
        raise ForbiddenError("You are not a member of this group")

    member_ids, names, paid, owed, s_paid, s_received = (
        await _load_group_balance_data(db, group_id)
    )

    net_balances = _compute_net_balances(member_ids, paid, owed, s_paid, s_received)

    member_balance_list = [
        MemberBalance(
            user_id=uid,
            display_name=names.get(uid, "Unknown"),
            net_balance=net_balances[uid],
        )
        for uid in member_ids
    ]

    simplified = _simplify_debts(net_balances, names)

    return GroupBalanceResponse(
        group_id=group_id,
        balances=member_balance_list,
        simplified_debts=simplified,
    )


async def get_my_balance(
    db: AsyncSession,
    group_id: UUID,
    current_user_id: UUID,
) -> MyBalanceResponse:
    """
    Return the current user's detailed balance breakdown within a group.
    """
    group = await group_repo.get_group_by_id(db, group_id)
    if group is None:
        raise NotFoundError("Group not found")

    membership = await group_repo.get_membership(db, group_id, current_user_id)
    if membership is None:
        raise ForbiddenError("You are not a member of this group")

    names = await balance_repo.get_user_names(db, [current_user_id])
    paid = await balance_repo.get_paid_totals(db, group_id)
    owed = await balance_repo.get_owed_totals(db, group_id)
    s_paid = await balance_repo.get_settlement_paid_totals(db, group_id)
    s_received = await balance_repo.get_settlement_received_totals(db, group_id)

    total_paid = paid.get(current_user_id, ZERO)
    total_owed = owed.get(current_user_id, ZERO)
    settlements_paid = s_paid.get(current_user_id, ZERO)
    settlements_received = s_received.get(current_user_id, ZERO)

    net = _normalize(total_paid - total_owed + settlements_paid - settlements_received)

    return MyBalanceResponse(
        group_id=group_id,
        user_id=current_user_id,
        display_name=names.get(current_user_id, "Unknown"),
        total_paid=_normalize(total_paid),
        total_owed=_normalize(total_owed),
        settlements_paid=_normalize(settlements_paid),
        settlements_received=_normalize(settlements_received),
        net_balance=net,
    )


async def user_has_nonzero_balance(
    db: AsyncSession,
    group_id: UUID,
    user_id: UUID,
) -> bool:
    """
    Return True if the user has a non-zero net balance in the group.
    Used by group_service to block leave/remove when balance is outstanding.
    """
    paid = await balance_repo.get_paid_totals(db, group_id)
    owed = await balance_repo.get_owed_totals(db, group_id)
    s_paid = await balance_repo.get_settlement_paid_totals(db, group_id)
    s_received = await balance_repo.get_settlement_received_totals(db, group_id)

    net = _normalize(
        paid.get(user_id, ZERO)
        - owed.get(user_id, ZERO)
        + s_paid.get(user_id, ZERO)
        - s_received.get(user_id, ZERO)
    )
    return net != ZERO
