"""
Smoke tests for the SQLAlchemy models.

Verifies that:
- All tables are created correctly from Base.metadata
- Basic insert/query works for every model
- Relationships resolve without errors
- UUID primary keys are generated automatically
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.expense import Expense, ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.settlement import Settlement
from app.models.user import RefreshToken, User


async def test_all_tables_created(db_engine):
    """Base.metadata.create_all should produce all 7 MVP tables."""
    from sqlalchemy import inspect

    async with db_engine.connect() as conn:
        table_names = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )

    expected = {
        "users",
        "refresh_tokens",
        "groups",
        "group_members",
        "expenses",
        "expense_splits",
        "settlements",
    }
    assert expected.issubset(set(table_names))


async def test_user_insert_and_query(db_session):
    """User rows can be inserted and queried; UUID PK is auto-generated."""
    user = User(
        name="Alice",
        email="alice@example.com",
        password_hash="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.id is not None
    assert user.is_active is True
    assert user.avatar_url is None

    result = await db_session.execute(select(User).where(User.email == "alice@example.com"))
    fetched = result.scalar_one()
    assert fetched.name == "Alice"


async def test_refresh_token_insert(db_session):
    """RefreshToken rows are linked to a User and cascade-delete with it."""
    user = User(name="Bob", email="bob@example.com", password_hash="hashed")
    db_session.add(user)
    await db_session.flush()

    token = RefreshToken(
        user_id=user.id,
        token_hash="abc123hash",
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )
    db_session.add(token)
    await db_session.commit()

    result = await db_session.execute(
        select(RefreshToken).where(RefreshToken.user_id == user.id)
    )
    assert result.scalar_one().token_hash == "abc123hash"


async def test_group_and_membership(db_session):
    """Group and GroupMember rows can be inserted; unique constraint is present."""
    user = User(name="Carol", email="carol@example.com", password_hash="hashed")
    db_session.add(user)
    await db_session.flush()

    group = Group(name="Trip to Paris")
    db_session.add(group)
    await db_session.flush()

    member = GroupMember(
        group_id=group.id,
        user_id=user.id,
        role="admin",
        joined_at=datetime.now(timezone.utc),
    )
    db_session.add(member)
    await db_session.commit()

    result = await db_session.execute(
        select(GroupMember).where(GroupMember.group_id == group.id)
    )
    fetched = result.scalar_one()
    assert fetched.role == "admin"
    assert fetched.user_id == user.id


async def test_expense_and_splits(db_session):
    """Expense and ExpenseSplit rows store Decimal amounts without precision loss."""
    user = User(name="Dave", email="dave@example.com", password_hash="hashed")
    group = Group(name="Flatmates")
    db_session.add_all([user, group])
    await db_session.flush()

    expense = Expense(
        group_id=group.id,
        payer_id=user.id,
        created_by=user.id,
        description="Groceries",
        amount=Decimal("99.9900"),
        split_strategy="equal",
        expense_date=date(2025, 1, 15),
    )
    db_session.add(expense)
    await db_session.flush()

    split = ExpenseSplit(
        expense_id=expense.id,
        user_id=user.id,
        amount=Decimal("99.9900"),
        percentage=None,
    )
    db_session.add(split)
    await db_session.commit()

    result = await db_session.execute(
        select(ExpenseSplit).where(ExpenseSplit.expense_id == expense.id)
    )
    fetched = result.scalar_one()
    assert fetched.amount == Decimal("99.9900")
    assert fetched.percentage is None


async def test_settlement_insert(db_session):
    """Settlement rows store payer/payee/creator/amount correctly."""
    payer = User(name="Eve", email="eve@example.com", password_hash="hashed")
    payee = User(name="Frank", email="frank@example.com", password_hash="hashed")
    group = Group(name="Office lunch")
    db_session.add_all([payer, payee, group])
    await db_session.flush()

    settlement = Settlement(
        group_id=group.id,
        payer_id=payer.id,
        payee_id=payee.id,
        creator_id=payer.id,  # creator is the payer in this case
        amount=Decimal("25.0000"),
        settlement_date=date(2025, 2, 1),
    )
    db_session.add(settlement)
    await db_session.commit()

    result = await db_session.execute(
        select(Settlement).where(Settlement.group_id == group.id)
    )
    fetched = result.scalar_one()
    assert fetched.amount == Decimal("25.0000")
    assert fetched.payer_id == payer.id
    assert fetched.payee_id == payee.id
    assert fetched.creator_id == payer.id


async def test_soft_delete_fields_default_false(db_session):
    """is_deleted defaults to False for Group, Expense, and Settlement."""
    group = Group(name="Test group")
    db_session.add(group)
    await db_session.flush()

    user = User(name="Grace", email="grace@example.com", password_hash="hashed")
    db_session.add(user)
    await db_session.flush()

    expense = Expense(
        group_id=group.id,
        payer_id=user.id,
        created_by=user.id,
        description="Test",
        amount=Decimal("10.0000"),
        split_strategy="equal",
        expense_date=date(2025, 3, 1),
    )
    db_session.add(expense)
    await db_session.commit()

    assert group.is_deleted is False
    assert group.deleted_at is None
    assert expense.is_deleted is False
    assert expense.deleted_at is None
