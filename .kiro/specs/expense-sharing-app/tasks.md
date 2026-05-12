# MVP Implementation Plan: Expense Sharing App

## Overview

Solo-developer MVP. Ship a working expense sharing app fast. Architecture stays modular
(routes → services → repositories) but without unnecessary abstractions — no generic base
classes, no Redis, no notifications, no audit logs, no property-based tests.

**In scope:** authentication, groups, expenses (all 3 split strategies), balance computation,
debt simplification, settlements, HTMX frontend.

**Deferred to v2:** notifications, Redis caching, search/filtering, avatar uploads, audit logs,
rate limiting, HSTS/security hardening, property-based tests.

---

## Milestones

| # | Milestone | Deliverable |
|---|---|---|
| M1 | Foundation | App boots, DB migrates, `/health` returns 200 |
| M2 | Auth | Register, login, JWT, protected routes all work |
| M3 | Groups | Full group + membership CRUD |
| M4 | Expenses | All 3 split strategies, Decimal arithmetic verified |
| M5 | Balances | Net balances + debt simplification correct |
| M6 | Settlements | Record and delete settlements, balance reversal works |
| M7 | Frontend | HTMX UI covers the full user journey end-to-end |
| M8 | Ship | Docker compose up, all integration tests green |

---

## Tasks

- [x] 1. Project scaffolding
  - Create folder structure: `app/api/v1/routes/`, `app/core/`, `app/db/`, `app/models/`,
    `app/repositories/`, `app/services/`, `app/schemas/`, `app/utils/`, `app/templates/`,
    `app/static/css/`, `app/static/js/`, `app/web/`, `tests/integration/`, `migrations/versions/`
  - Add `__init__.py` to every package folder
  - Create `pyproject.toml` with pinned dependencies:
    - Runtime: `fastapi==0.115.*`, `uvicorn[standard]==0.30.*`, `sqlalchemy[asyncio]==2.0.*`,
      `asyncpg==0.29.*`, `alembic==1.13.*`, `passlib[bcrypt]==1.7.*`,
      `python-jose[cryptography]==3.3.*`, `pydantic[email]==2.*`, `pydantic-settings==2.*`,
      `jinja2==3.1.*`, `python-multipart==0.0.*`
    - Dev/test: `httpx==0.27.*`, `pytest==8.*`, `pytest-asyncio==0.23.*`, `aiosqlite==0.20.*`
  - Create `app/core/config.py` using `pydantic-settings`: fields `DATABASE_URL`, `JWT_SECRET`
    (validated `min_length=32` at startup), `JWT_ALGORITHM="HS256"`,
    `ACCESS_TOKEN_EXPIRE_MINUTES=15`, `REFRESH_TOKEN_EXPIRE_DAYS=7`, `DEBUG=False`,
    `APP_VERSION="0.1.0"`; expose a module-level `settings = Settings()` singleton
  - Create `.env.example` listing every env var with placeholder values and inline comments
  - Create `Dockerfile`: multi-stage — `builder` stage installs deps with `pip install`,
    `final` stage is `python:3.12-slim`, copies only the installed packages and `app/`
  - Create `docker-compose.yml`: services `app` (builds from Dockerfile, depends on `db`),
    `db` (postgres:16-alpine, named volume, healthcheck); expose app on port 8000
  - Create `docker-compose.override.yml`: mount `./app:/app/app` for live reload in dev,
    set `DEBUG=true`, `uvicorn --reload`
  - Create `app/main.py`: instantiate `FastAPI(title="Expense Sharing", version=settings.APP_VERSION)`,
    register exception handlers (stubs), add `@app.on_event("startup")` that logs config summary;
    mount a stub router so the app starts without errors
  - Create `app/api/v1/routes/health.py`: `GET /health` — run `SELECT 1` via `get_db()`;
    return `{"status": "ok", "db": "ok"}` on success or HTTP 503 `{"status": "degraded", "db": "error"}`
    on `OperationalError`; register this router in `app/main.py`
  - Create `tests/conftest.py`: async SQLite in-memory engine for tests, override `get_db`
    dependency, `AsyncClient` fixture pointing at the FastAPI app; use `pytest-asyncio` in
    `asyncio_mode = "auto"`
  - _Requirements: 19.1, 19.2, 19.3, 19.5, 20.1, 20.2_

- [x] 2. Database models and initial migration
  - Create `app/db/base.py`: async `DeclarativeBase` subclass; add `TimestampMixin` with
    `created_at: Mapped[datetime]` (`server_default=func.now()`) and
    `updated_at: Mapped[datetime]` (`server_default=func.now(), onupdate=func.now()`)
  - Create `app/db/session.py`: create async engine from `settings.DATABASE_URL`;
    `AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)`;
    `async def get_db() -> AsyncGenerator[AsyncSession, None]` — yields a session, always closes
  - Implement all MVP models (each in its own file, inheriting `Base` and `TimestampMixin`
    where applicable):
    - `app/models/user.py`:
      - `User`: `id` (UUID PK, default `uuid4`), `name` (String 255), `email` (String 255,
        unique, indexed), `password_hash` (String 255), `avatar_url` (String 512, nullable),
        `is_active` (Boolean, default True), timestamps
      - `RefreshToken`: `id` (UUID PK), `user_id` (FK → users.id, cascade delete), `token_hash`
        (String 255, unique), `expires_at` (DateTime), `created_at`
    - `app/models/group.py`:
      - `Group`: `id`, `name` (String 255), `description` (Text, nullable), `is_deleted`
        (Boolean, default False), `deleted_at` (DateTime, nullable), timestamps
      - `GroupMember`: `id`, `group_id` (FK → groups.id), `user_id` (FK → users.id),
        `role` (String 20 — `"admin"` or `"member"`), `joined_at` (DateTime, server_default);
        `UniqueConstraint("group_id", "user_id")`
    - `app/models/expense.py`:
      - `Expense`: `id`, `group_id` (FK), `payer_id` (FK → users.id), `created_by` (FK → users.id),
        `description` (String 500), `amount` (`Numeric(19,4)`), `split_strategy` (String 20),
        `expense_date` (Date), `is_deleted` (Boolean, default False), `deleted_at` (nullable),
        timestamps; `CheckConstraint("amount > 0", name="ck_expense_positive_amount")`
      - `ExpenseSplit`: `id`, `expense_id` (FK → expenses.id, cascade delete), `user_id` (FK),
        `amount` (`Numeric(19,4)`), `percentage` (`Numeric(7,4)`, nullable);
        `CheckConstraint("amount >= 0", name="ck_split_non_negative")`
    - `app/models/settlement.py`:
      - `Settlement`: `id`, `group_id` (FK), `payer_id` (FK → users.id), `payee_id` (FK → users.id),
        `amount` (`Numeric(19,4)`), `settlement_date` (Date), `is_deleted` (Boolean, default False),
        `deleted_at` (nullable), `created_at`;
        `CheckConstraint("amount > 0", name="ck_settlement_positive_amount")`,
        `CheckConstraint("payer_id != payee_id", name="ck_settlement_different_users")`
  - Create `app/models/__init__.py` that imports all model classes (required for Alembic autogenerate)
  - Configure `migrations/env.py`: import `Base` from `app/db/base`, import `app/models/__init__`,
    use `run_async_migrations()` pattern for async engine; set `target_metadata = Base.metadata`
  - Run `alembic revision --autogenerate -m "initial"` and review the generated SQL — confirm
    all FK constraints, check constraints, and unique indexes are present
  - Add startup check in `app/main.py` `@app.on_event("startup")`: query `alembic_version`,
    compare to `script.get_current_head()`; log `WARNING` if schema is behind
  - _Requirements: 15.4, 18.1, 18.2, 18.3, 18.4_

- [x] 3. Auth — register, login, JWT, protected routes
  - Create `app/core/security.py` — pure functions, no DB access:
    - `hash_password(plain: str) -> str` — bcrypt via passlib `CryptContext`
    - `verify_password(plain: str, hashed: str) -> bool`
    - `create_access_token(user_id: UUID) -> str` — HS256, expiry from `settings`
    - `create_refresh_token(user_id: UUID) -> str` — HS256, 7-day expiry
    - `decode_token(token: str) -> dict` — raises `UnauthorizedError` on expired/invalid/tampered
  - Create `app/core/exceptions.py`:
    - `AppException(Exception)`: fields `status_code: int`, `detail: str`
    - Subclasses: `NotFoundError(404)`, `ConflictError(409)`, `ForbiddenError(403)`,
      `UnauthorizedError(401)`, `ValidationError(422)`
  - Register exception handlers in `app/main.py`:
    - `AppException` → `JSONResponse({"detail": exc.detail, "status": exc.status_code})`
    - Unhandled `Exception` → log full traceback, return 500 `{"detail": "Internal server error"}`
  - Create `app/schemas/auth.py`: `RegisterRequest` (name, email, password min_length=8),
    `LoginRequest` (email, password), `TokenPair` (access_token, refresh_token, token_type),
    `AccessToken` (access_token, token_type)
  - Create `app/schemas/users.py`: `UserPublic` (id, name, email, avatar_url, created_at),
    `UpdateProfileRequest` (name: optional)
  - Create `app/repositories/user_repository.py` — typed async functions, no business logic:
    - `get_by_id(db, user_id) -> User | None`
    - `get_by_email(db, email) -> User | None`
    - `create(db, name, email, password_hash) -> User`
    - `update(db, user, **fields) -> User`
  - Create `app/services/auth_service.py`:
    - `register(db, data: RegisterRequest) -> UserPublic` — `get_by_email` → 409 if exists,
      `hash_password`, `user_repo.create`, return `UserPublic`
    - `login(db, data: LoginRequest) -> TokenPair` — `get_by_email` → 401 if not found,
      `verify_password` → 401 if wrong, create both tokens, hash refresh token, insert into
      `refresh_tokens` with `expires_at`, return `TokenPair`
    - `refresh(db, token: str) -> AccessToken` — `decode_token` → 401, hash token, query
      `refresh_tokens` → 401 if not found or expired, issue new access token
    - `logout(db, user_id, token: str)` — hash token, delete matching `refresh_tokens` row
    - `get_current_user(db, token: str) -> User` — `decode_token`, `get_by_id` → 401 if not found
  - Create `app/api/v1/dependencies.py`:
    - `get_db` — re-export from `app/db/session`
    - `get_current_user(token: str = Depends(OAuth2PasswordBearer), db = Depends(get_db)) -> User`
    - `require_group_member(group_id: UUID, current_user, db) -> GroupMember` — 404 if group
      not found, 403 if user not a member
    - `require_group_admin(membership: GroupMember = Depends(require_group_member)) -> GroupMember`
      — 403 if role != "admin"
  - Create `app/api/v1/routes/auth.py` (prefix `/api/v1/auth`):
    - `POST /register` → 201 `UserPublic`
    - `POST /login` → 200 `TokenPair`
    - `POST /refresh` → 200 `AccessToken`
    - `POST /logout` → 204
  - Create `app/api/v1/routes/users.py` (prefix `/api/v1/users`):
    - `GET /me` → 200 `UserPublic`
    - `PATCH /me` → 200 `UserPublic` (name only; avatar deferred to v2)
  - Register both routers in `app/main.py`
  - Write `tests/integration/test_auth.py`:
    - Register → 201; duplicate email → 409; short password → 422; bad email → 422
    - Login with correct creds → 200 with both tokens; wrong password → 401; unknown email → 401
    - Access `GET /users/me` with valid token → 200; with no token → 401; with expired token → 401
    - Refresh with valid token → 200 new access token; with invalid token → 401
    - Logout → 204; reuse refresh token after logout → 401
    - Tamper JWT signature → 401
  - _Requirements: 1.1–1.5, 2.1–2.8, 3.1, 3.2, 3.5, 17.1, 17.6_

- [x] 4. Groups — CRUD and membership
  - Create `app/schemas/groups.py`:
    - `CreateGroupRequest` (name: str, description: str | None)
    - `UpdateGroupRequest` (name: str | None, description: str | None)
    - `MemberOut` (user_id, name, email, role, joined_at)
    - `GroupDetail` (id, name, description, role, member_count, members: list[MemberOut], created_at)
    - `GroupSummary` (id, name, member_count, your_balance: Decimal)
  - Create `app/repositories/group_repository.py` — typed async functions:
    - `create(db, name, description, creator_id) -> Group` — insert group + GroupMember(role="admin")
      in one transaction
    - `get_by_id(db, group_id) -> Group | None` — filter `is_deleted=False`
    - `get_membership(db, group_id, user_id) -> GroupMember | None`
    - `list_for_user(db, user_id) -> list[Group]` — join `group_members`, filter active groups
    - `add_member(db, group_id, user_id, role="member") -> GroupMember`
    - `remove_member(db, group_id, user_id) -> None`
    - `update(db, group, **fields) -> Group`
    - `soft_delete(db, group) -> None` — set `is_deleted=True`, `deleted_at=now()`
  - Create `app/services/group_service.py`:
    - `create_group(db, creator_id, data) -> GroupDetail`
    - `get_group(db, user_id, group_id) -> GroupDetail` — 404 if not found, 403 if not member
    - `list_user_groups(db, user_id) -> list[GroupSummary]` — compute `your_balance` with a
      simple inline SQL aggregate (no cache); positive = owed to you, negative = you owe
    - `add_member(db, admin_id, group_id, email) -> list[MemberOut]` — 404 if user not found,
      409 if already a member
    - `remove_member(db, admin_id, group_id, member_id)` — compute member's net balance in
      group; 409 if non-zero, else remove
    - `update_group(db, admin_id, group_id, data) -> GroupDetail`
    - `delete_group(db, admin_id, group_id)` — check no outstanding debts (any non-zero balance
      in group → 409), soft-delete
  - Create `app/api/v1/routes/groups.py` (prefix `/api/v1/groups`):
    - `POST /` → 201 `GroupDetail`
    - `GET /` → 200 `list[GroupSummary]`
    - `GET /{group_id}` → 200 `GroupDetail`
    - `PATCH /{group_id}` → 200 `GroupDetail` (admin only)
    - `DELETE /{group_id}` → 200 (admin only)
    - `POST /{group_id}/members` body `{email}` → 200 `list[MemberOut]` (admin only)
    - `DELETE /{group_id}/members/{user_id}` → 200 (admin only)
  - Register router in `app/main.py`
  - Write `tests/integration/test_groups.py`:
    - Create group → creator is admin in response
    - Add member by email → appears in member list with role "member"
    - Non-admin add/remove/update/delete → 403
    - Remove member with zero balance → 200; with non-zero balance → 409
    - Delete group with no debts → 200; with outstanding debts → 409
    - List groups returns only groups the user belongs to
  - _Requirements: 4.1–4.9_

- [x] 5. Decimal split utilities
  - Create `app/utils/decimal_utils.py` — pure functions, no DB or FastAPI imports:
    - `compute_equal_splits(total: Decimal, participant_ids: list[UUID]) -> dict[UUID, Decimal]`
      — `share = (total / len(participants)).quantize(Decimal("0.0001"), ROUND_DOWN)`;
      `remainder = total - share * len(participants)`; add remainder to `participant_ids[0]`;
      assert `sum(result.values()) == total` before returning
    - `compute_exact_splits(splits: list[SplitInput]) -> dict[UUID, Decimal]`
      — sum all amounts; if `abs(total - sum) > Decimal("0.01")` raise `ValidationError`;
      return `{s.user_id: s.amount for s in splits}`
    - `compute_percentage_splits(total: Decimal, splits: list[PercentageSplitInput]) -> dict[UUID, Decimal]`
      — validate `sum(percentages) == 100` (within 0.0001 tolerance) → `ValidationError`;
      `share = (total * pct / 100).quantize(Decimal("0.0001"), ROUND_DOWN)` per participant;
      assign remainder to first participant; assert sum equals total
  - Create `app/utils/pagination.py`:
    - `class Page(BaseModel, Generic[T])`: fields `items: list[T]`, `total: int`, `page: int`,
      `page_size: int`, `pages: int`
    - `async def paginate(query, db: AsyncSession, page: int, page_size: int = 20) -> Page[T]`
      — run count query, then offset/limit query; return `Page`
  - Write `tests/integration/test_decimal_utils.py`:
    - Equal split: `Decimal("10.00")` among 3 → splits sum exactly to `10.00`
    - Equal split: `Decimal("0.10")` among 3 → splits sum exactly to `0.10`
    - Percentage split: 33.33% / 33.33% / 33.34% of `Decimal("100.00")` → sums to `100.00`
    - Percentage split: percentages sum to 99 → `ValidationError`
    - Exact split: amounts sum to total → returned as-is
    - Exact split: amounts off by 0.02 → `ValidationError`
  - _Requirements: 5.7, 6.1–6.5_

- [x] 6. Expenses — CRUD with split strategies
  - Create `app/schemas/expenses.py`:
    - `SplitInput` (user_id: UUID, amount: Decimal)
    - `PercentageSplitInput` (user_id: UUID, percentage: Decimal)
    - `CreateExpenseRequest` (description: str, amount: Decimal gt=0, payer_id: UUID,
      expense_date: date, split_strategy: Literal["equal","exact","percentage"],
      participants: list[UUID] | None, splits: list[SplitInput] | None,
      percentage_splits: list[PercentageSplitInput] | None)
    - `UpdateExpenseRequest` — same fields, all optional
    - `SplitDetail` (user_id, name, amount, percentage)
    - `ExpenseDetail` (id, group_id, payer_id, payer_name, description, amount, split_strategy,
      expense_date, splits: list[SplitDetail], created_at)
  - Create `app/repositories/expense_repository.py`:
    - `create(db, group_id, payer_id, created_by, description, amount, split_strategy,
      expense_date, splits: dict[UUID, Decimal], percentages: dict[UUID, Decimal] | None) -> Expense`
      — insert `Expense` + all `ExpenseSplit` rows in one `async with db.begin()` block
    - `get_by_id(db, expense_id) -> Expense | None` — eager-load splits
    - `list_for_group(db, group_id, page) -> Page[Expense]` — `is_deleted=False`,
      order `expense_date DESC, created_at DESC`, paginate at 20
    - `update(db, expense, fields, splits, percentages) -> Expense` — delete old splits,
      insert new splits, update expense fields; all in one transaction
    - `soft_delete(db, expense) -> None`
  - Create `app/services/expense_service.py`:
    - `create_expense(db, user_id, group_id, data: CreateExpenseRequest) -> ExpenseDetail`
      — verify group exists and user is member (403); verify payer is group member (422);
      verify all split participants are group members (422); dispatch to correct split utility;
      call `expense_repo.create`; return `ExpenseDetail`
    - `get_expense(db, user_id, expense_id) -> ExpenseDetail` — 404 if not found, 403 if
      user not in group
    - `list_expenses(db, user_id, group_id, page) -> Page[ExpenseDetail]`
    - `update_expense(db, user_id, expense_id, data) -> ExpenseDetail` — 403 if not payer
      or admin; recompute splits; call `expense_repo.update`
    - `delete_expense(db, user_id, expense_id)` — 403 if not payer or admin; soft-delete
  - Create `app/api/v1/routes/expenses.py` (prefix `/api/v1/groups/{group_id}/expenses`):
    - `POST /` → 201 `ExpenseDetail`
    - `GET /` → 200 `Page[ExpenseDetail]`
    - `GET /{expense_id}` → 200 `ExpenseDetail`
    - `PATCH /{expense_id}` → 200 `ExpenseDetail`
    - `DELETE /{expense_id}` → 200
  - Register router in `app/main.py`
  - Write `tests/integration/test_expenses.py`:
    - Create with equal split → splits sum exactly to total, strategy stored as "equal"
    - Create with exact split → each amount stored as provided
    - Create with percentage split → splits sum exactly to total
    - Amount = 0 → 422; negative amount → 422
    - Participant not in group → 422; payer not in group → 422
    - Percentage splits don't sum to 100 → 422; exact splits don't sum to total → 422
    - List is reverse-chronological, max 20 per page
    - Non-payer non-admin edit → 403; non-payer non-admin delete → 403
    - Soft-deleted expense excluded from list
  - _Requirements: 5.1–5.7, 6.1–6.6, 7.1–7.3, 15.1_

- [x] 7. Balance computation and debt simplification
  - Create `app/schemas/balances.py`:
    - `MemberBalance` (user_id: UUID, name: str, net_amount: Decimal)
      — positive = owed money, negative = owes money
    - `CounterpartyBalance` (user_id: UUID, name: str, net_amount: Decimal)
    - `DebtItem` (from_user_id: UUID, from_name: str, to_user_id: UUID, to_name: str, amount: Decimal)
  - Create `app/repositories/balance_repository.py`:
    - `compute_group_balances(db, group_id) -> dict[UUID, Decimal]`
      — single SQL query using `COALESCE` and `SUM` with `CAST(... AS NUMERIC)`:
      ```sql
      -- paid by user (from non-deleted expenses)
      SUM(e.amount) WHERE e.payer_id = user AND e.is_deleted = false
      -- owed by user (from non-deleted splits)
      - SUM(es.amount) WHERE es.user_id = user AND e.is_deleted = false
      -- received settlements
      + SUM(s.amount) WHERE s.payee_id = user AND s.is_deleted = false
      -- paid settlements
      - SUM(s.amount) WHERE s.payer_id = user AND s.is_deleted = false
      ```
      Return `dict[user_id, Decimal]` for all group members (include zero-balance members)
    - `compute_user_overall_balances(db, user_id) -> dict[UUID, Decimal]`
      — aggregate net balance per counterparty across all groups the user belongs to;
      use a single query joining `group_members`, `expenses`, `expense_splits`, `settlements`
  - Create `app/services/balance_service.py`:
    - `get_group_balances(db, user_id, group_id) -> list[MemberBalance]`
      — verify user is group member (403); call repo; join user names; sort by `net_amount DESC`
    - `get_user_overall_balances(db, user_id) -> list[CounterpartyBalance]`
      — call repo; join user names; exclude zero-balance counterparties; sort by abs(net_amount) DESC
    - `get_simplified_debts(db, user_id, group_id) -> list[DebtItem]`
      — load group balances; run greedy min-cash-flow algorithm:
        1. Split into `creditors` (net > 0) and `debtors` (net < 0), sort by abs value desc
        2. While both lists non-empty: match largest creditor with largest debtor
        3. Create `DebtItem(from=debtor, to=creditor, amount=min(abs(debtor), creditor))`
        4. Reduce both balances; remove if zero; repeat
      — result has at most N-1 debts; return empty list if all balances are zero
  - Create `app/api/v1/routes/balances.py`:
    - `GET /api/v1/groups/{group_id}/balances` → 200 `list[MemberBalance]`
    - `GET /api/v1/groups/{group_id}/balances/simplified` → 200 `list[DebtItem]`
    - `GET /api/v1/users/me/balances` → 200 `list[CounterpartyBalance]`
  - Register router in `app/main.py`
  - Write `tests/integration/test_balances.py`:
    - Two users, one expense (equal split): payer has +50, other has -50
    - Add settlement of 50: both balances go to 0
    - Delete expense: balances revert to pre-expense state
    - Delete settlement: balances revert to post-expense state
    - Soft-deleted expense excluded from balance
    - Simplified debts: 3-person group, verify result has ≤ 2 debts and applying them zeroes all balances
    - Empty group: all balances are 0, simplified debts is empty list
    - Overall balance: user in 2 groups, verify per-counterparty aggregation
  - _Requirements: 8.1–8.6, 9.1–9.3_

- [x] 8. Settlements — record and delete
  - Create `app/schemas/settlements.py`:
    - `CreateSettlementRequest` (payer_id: UUID, payee_id: UUID, amount: Decimal gt=0,
      settlement_date: date)
    - `SettlementDetail` (id, group_id, payer_id, payer_name, payee_id, payee_name, amount,
      settlement_date, created_at)
  - Create `app/repositories/settlement_repository.py`:
    - `create(db, group_id, payer_id, payee_id, amount, settlement_date) -> Settlement`
      — insert in `async with db.begin()` block
    - `get_by_id(db, settlement_id) -> Settlement | None`
    - `list_for_group(db, group_id, page) -> Page[Settlement]` — `is_deleted=False`,
      order `settlement_date DESC, created_at DESC`, paginate at 20
    - `soft_delete(db, settlement) -> None`
  - Create `app/services/settlement_service.py`:
    - `create_settlement(db, user_id, group_id, data) -> SettlementDetail`
      — verify group exists and user is member (403); validate `amount > 0` (422);
      validate `payer_id != payee_id` (422); verify both payer and payee are group members (422);
      call `settlement_repo.create`; return `SettlementDetail`
    - `delete_settlement(db, user_id, settlement_id)` — 404 if not found; 403 if user is
      not the payer and not a group admin; soft-delete
    - `list_settlements(db, user_id, group_id, page) -> Page[SettlementDetail]`
      — verify user is group member (403)
  - Create `app/api/v1/routes/settlements.py` (prefix `/api/v1/groups/{group_id}/settlements`):
    - `POST /` → 201 `SettlementDetail`
    - `GET /` → 200 `Page[SettlementDetail]`
    - `DELETE /{settlement_id}` → 200
  - Register router in `app/main.py`
  - Write `tests/integration/test_settlements.py`:
    - Create settlement → 201; verify balance changes (payer balance increases, payee decreases)
    - Delete settlement → balance reverts to pre-settlement state
    - Amount = 0 → 422; negative amount → 422
    - Payer == payee → 422
    - Payer or payee not in group → 422
    - Non-payer non-admin delete → 403
    - List is reverse-chronological, paginated at 20
  - _Requirements: 10.1–10.5, 15.2, 15.3_

- [x] 9. HTMX/Jinja2 frontend
  - Create `app/web/routes.py` as a separate `APIRouter` (no `/api/v1/` prefix) for browser
    routes; register it in `app/main.py` after the API routers
  - Auth middleware for web routes: `app/web/auth.py` — `get_current_user_from_cookie(request)`
    reads `access_token` cookie, decodes JWT; if missing or expired, redirect to `/login`
  - Create `app/templates/base.html`:
    - TailwindCSS CDN `<link>` in `<head>`
    - HTMX CDN `<script>` before `</body>`
    - Nav bar: app name, current user's name, logout button (`hx-post="/logout"`)
    - `{% block content %}{% endblock %}`
    - Flash message block (read from cookie or query param)
  - Auth templates (full-page, standard form POST — no HTMX needed):
    - `app/templates/auth/login.html` — email + password form, inline field errors
    - `app/templates/auth/register.html` — name + email + password form, inline field errors
  - Dashboard template:
    - `app/templates/dashboard/index.html` — table of user's groups: name, member count,
      your balance (green if positive, red if negative), link to group detail
  - Group templates:
    - `app/templates/groups/detail.html` — tabs or sections: Members, Expenses, Balances,
      Settle Up; "Add Expense" button opens expense form; "Settle Up" button opens settlement form
    - `app/templates/groups/form.html` — create/edit group (name, description)
    - `app/templates/groups/_member_row.html` — HTMX partial: one `<tr>` for a member
  - Expense templates:
    - `app/templates/expenses/form.html` — description, amount, payer dropdown, date,
      split strategy `<select hx-get="/expenses/split-inputs" hx-target="#split-inputs"
      hx-trigger="change">`; `<div id="split-inputs">` swapped by HTMX
    - `app/templates/expenses/_equal_inputs.html` — checkboxes for each group member
    - `app/templates/expenses/_exact_inputs.html` — number input per member
    - `app/templates/expenses/_percentage_inputs.html` — percentage input per member,
      live sum display
    - `app/templates/expenses/_row.html` — one expense row partial (HTMX list prepend)
  - Settlement templates:
    - `app/templates/settlements/form.html` — payer dropdown, payee dropdown, amount, date
    - `app/templates/settlements/_row.html` — one settlement row partial
  - Web routes in `app/web/routes.py`:
    - `GET /` → redirect to `/dashboard` (authenticated) or `/login`
    - `GET /login`, `POST /login` — on success set `HttpOnly` cookie `access_token`, redirect
      to `/dashboard`; on failure re-render login template with error
    - `GET /register`, `POST /register` — on success redirect to `/login`
    - `POST /logout` — delete `access_token` cookie, redirect to `/login`
    - `GET /dashboard` — render dashboard with `list_user_groups`
    - `GET /groups/new` → render `groups/form.html`
    - `POST /groups` → create group, redirect to `/groups/{id}`
    - `GET /groups/{group_id}` → render `groups/detail.html` with expenses, balances, members
    - `PATCH /groups/{group_id}` → update, return `groups/detail.html` partial (HTMX swap)
    - `DELETE /groups/{group_id}` → soft-delete, redirect to `/dashboard`
    - `POST /groups/{group_id}/members` → add member, return `_member_row.html` partial
    - `DELETE /groups/{group_id}/members/{user_id}` → remove, return updated member list partial
    - `GET /groups/{group_id}/expenses/new` → render `expenses/form.html`
    - `GET /expenses/split-inputs` → return the correct split input partial based on `?strategy=`
    - `POST /groups/{group_id}/expenses` → create expense; on success return `_row.html` partial
      (HTMX prepends to list); on validation error return form partial with inline errors
    - `PATCH /groups/{group_id}/expenses/{expense_id}` → update, return updated `_row.html`
    - `DELETE /groups/{group_id}/expenses/{expense_id}` → soft-delete, remove row via HTMX
    - `GET /groups/{group_id}/settlements/new` → render `settlements/form.html`
    - `POST /groups/{group_id}/settlements` → create, return `_row.html` partial
    - `DELETE /groups/{group_id}/settlements/{settlement_id}` → soft-delete, remove row
  - _Requirements: 14.1–14.5_

- [x] 10. Docker wiring and final integration test pass
  - Add `alembic upgrade head` as the entrypoint command before `uvicorn` starts (use a
    shell script `entrypoint.sh` or `CMD ["sh", "-c", "alembic upgrade head && uvicorn ..."]`)
  - Verify `docker compose up` starts cleanly: DB healthy → migrations run → app starts →
    `GET /health` returns 200
  - Verify OpenAPI schema at `/api/v1/openapi.json` and Swagger UI at `/api/v1/docs`
  - Write `tests/integration/test_full_flow.py` — end-to-end happy path:
    1. Register user A and user B
    2. User A creates a group, adds user B
    3. User A creates an expense of $90 (equal split) — A paid, A owes $45, B owes $45
    4. Check balances: A net = +$45, B net = -$45
    5. Check simplified debts: one debt B → A $45
    6. User B records a settlement of $45 to A
    7. Check balances: both 0
    8. User A deletes the expense
    9. Check balances: A net = -$45, B net = +$45 (settlement still exists)
    10. User B deletes the settlement
    11. Check balances: both 0
  - Fix any issues found during the full-flow test run
  - _Requirements: 13.1, 13.2, 19.1, 19.2, 20.1_

---

## Implementation Order

```
Task 1  →  Task 2  →  Task 3  →  Task 4
(scaffold)  (models)   (auth)    (groups)
                                    ↓
                              Task 5 (decimal utils)
                                    ↓
                              Task 6 (expenses)
                                    ↓
                              Task 7 (balances)
                                    ↓
                              Task 8 (settlements)
                                    ↓
                              Task 9 (frontend)
                                    ↓
                              Task 10 (Docker + final tests)
```

Each task ends with integration tests that must pass before moving to the next.
Tasks 1–8 are API-only and testable without a browser.

---

## Future Upgrade Path (v2)

| Feature | Effort | What to add |
|---|---|---|
| Redis caching | Low | Add `get_cache()` dep; wrap `balance_service` reads with cache-aside; call `invalidate_group_cache()` in expense/settlement writes |
| Search & filtering | Low | Extend `expense_repository.list_for_group` with optional `keyword` (ILIKE), `date_from`, `date_to`, `payer_id` params |
| Avatar uploads | Low | `POST /users/me/avatar`; validate JPEG/PNG ≤ 5 MB; store on disk or S3 |
| Notifications / activity feed | Medium | Add `Notification` model + repo + service; wire fan-out into expense/settlement writes |
| Audit log | Medium | Add `AuditLog` model; call `audit_service.record(...)` in expense/settlement update/delete |
| Rate limiting | Low | Add `slowapi` middleware; 100 req/min per IP → 429 |
| Security hardening | Low | HSTS header middleware; HTML entity escaping helper in service write paths |
| Property-based tests | Medium | Add `hypothesis`; implement Properties 1–36 from `design.md` |
| Mobile API | Low | `/api/v1/` routes are already API-first; add versioned response schemas, mobile token flow |

---

## Notes

- All monetary values use `decimal.Decimal` — never `float`
- All write operations use `async with db.begin():` for automatic rollback on failure
- No generic repository base class — each repository is a plain module with typed async functions
- No Redis in MVP — balance queries hit the DB directly; add caching in v2
- No `AuditLog` or `Notification` models in MVP — schema is forward-compatible, add in v2
- JWT stored in `HttpOnly` cookie for web routes; Bearer token for `/api/v1/` routes
- Pydantic v2 models with type hints everywhere
- Keep each file under ~200 lines; split into sub-modules if it grows beyond that
- Test DB uses SQLite in-memory via `aiosqlite` (fast, no Docker needed for unit/integration tests)
