"""
Shared pytest fixtures for all integration tests.

Uses an in-memory SQLite database (via aiosqlite) so tests run fast
without needing a running PostgreSQL instance.

The `get_db` FastAPI dependency is overridden to use the test session,
ensuring every test gets a clean, isolated database state.

Each test gets a fresh schema via `db_engine` (function-scoped) and a
session that is closed — but not committed — after the test, keeping
tests fully isolated from one another.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.main import app

# SQLite in-memory database for tests.
# Each test function gets its own engine so the schema is always clean.
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_engine():
    """
    Create a fresh in-memory SQLite engine with the full schema for each test.
    Dropped and disposed after the test completes.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    """
    Yield an AsyncSession bound to the test engine.
    The session is closed after each test; no data persists between tests
    because each test gets its own in-memory engine.
    """
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(db_session: AsyncSession):
    """
    AsyncClient wired to the FastAPI app with the test DB session injected.

    The `get_db` dependency is overridden so every request in a test
    uses the same in-memory session — no real PostgreSQL needed.
    """

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    # Always restore the real dependency after the test
    app.dependency_overrides.clear()
