from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class MemberBalance(BaseModel):
    """Net balance for one group member."""

    user_id: UUID
    display_name: str
    # Positive = this member is owed money.
    # Negative = this member owes money.
    net_balance: Decimal


class SimplifiedDebt(BaseModel):
    """A single directional payment that reduces debts."""

    from_user_id: UUID
    from_name: str
    to_user_id: UUID
    to_name: str
    amount: Decimal  # always positive


class GroupBalanceResponse(BaseModel):
    group_id: UUID
    balances: list[MemberBalance]
    simplified_debts: list[SimplifiedDebt]


class MyBalanceResponse(BaseModel):
    """Current user's balance within a group."""

    group_id: UUID
    user_id: UUID
    display_name: str
    total_paid: Decimal       # sum of expenses where user is payer
    total_owed: Decimal       # sum of splits assigned to user
    settlements_paid: Decimal  # sum of settlements where user is payer
    settlements_received: Decimal  # sum of settlements where user is payee
    net_balance: Decimal      # total_paid - total_owed + settlements_paid - settlements_received
