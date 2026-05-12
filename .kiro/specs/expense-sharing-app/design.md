# Design Document: Expense Sharing App

## Overview

The Expense Sharing App is a production-grade web application inspired by Splitwise. It enables users to create groups, record shared expenses with multiple split strategies, track balances, simplify debts, and record settlements. The system exposes a versioned REST API (`/api/v1/`) consumed by an HTMX/Jinja2 frontend and designed for future mobile client integration.

### Key Design Goals

- **Precision**: All monetary values use Python `decimal.Decimal` — never `float`.
- **Correctness**: Financial operations are atomic; partial failures roll back entirely.
- **Performance**: Redis caches balance computations with automatic invalidation.
- **Security**: JWT-based stateless auth, bcrypt password hashing, rate limiting, XSS sanitization.
- **Maintainability**: Clean architecture with strict layer separation — routes never contain business logic.

### Technology Stack

| Layer | Technology |
|---|---|
| Web Framework | FastAPI (async) |
| ORM | SQLAlchemy 2.0 (async) |
| Database | PostgreSQL |
| Cache | Redis |
| Frontend | HTMX + Jinja2 + TailwindCSS |
| Auth | JWT (HS256, python-jose) |
| Migrations | Alembic |
| Containerization | Docker + docker-compose |
| Dependency Management | uv / poetry |
| Password Hashing | bcrypt (passlib) |
| Validation | Pydantic v2 |

---

## Architecture

The application follows **Clean Architecture** principles with four distinct layers. Dependencies flow inward: routes → services → repositories → models. No layer may import from a layer outside it.

```mermaid
graph TD
    subgraph "Presentation Layer"
        A[API Routes /api/v1/]
        B[HTMX Templates /templates/]
    end
    subgraph "Service Layer"
        C[Auth_Service]
        D[User_Service]
        E[Group_Service]
        F[Expense_Service]
        G[Balance_Service]
        H[Settlement_Service]
        I[Notification_Service]
    end
    subgraph "Repository Layer"
        J[UserRepository]
        K[GroupRepository]
        L[ExpenseRepository]
        M[BalanceRepository]
        N[SettlementRepository]
        O[NotificationRepository]
    end
    subgraph "Infrastructure Layer"
        P[(PostgreSQL)]
        Q[(Redis Cache)]
    end

    A --> C & D & E & F & G & H & I
    B --> C & D & E & F & G & H & I
    C & D --> J
    E --> K & J
    F --> L & K & G
    G --> M & Q
    H --> N & G
    I --> O
    J & K & L & M & N & O --> P
```

### Request Lifecycle

```mermaid
sequenceDiagram
    participant Client
    participant Middleware
    participant Route
    participant Service
    participant Repository
    participant DB
    participant Cache

    Client->>Middleware: HTTP Request
    Middleware->>Middleware: Attach X-Request-ID, rate-limit check, JWT validation
    Middleware->>Route: Validated request + current_user
    Route->>Service: Call service method (no business logic in route)
    Service->>Cache: Check cache (read operations)
    alt Cache hit
        Cache-->>Service: Cached result
    else Cache miss
        Service->>Repository: Query
        Repository->>DB: SQL via SQLAlchemy
        DB-->>Repository: ORM objects
        Repository-->>Service: Domain objects
        Service->>Cache: Store result
    end
    Service-->>Route: Result / raises HTTPException
    Route-->>Client: JSON response + X-Request-ID header
```

### Folder Structure

```
app/
  api/
    v1/
      routes/
        auth.py
        users.py
        groups.py
        expenses.py
        settlements.py
        balances.py
        notifications.py
      dependencies.py       # FastAPI Depends() factories
  core/
    config.py               # Pydantic Settings from env vars
    security.py             # JWT encode/decode, bcrypt helpers
    middleware.py           # Request ID, rate limiting, logging
    exceptions.py           # Custom exception classes + handlers
  db/
    session.py              # Async SQLAlchemy engine + session factory
    base.py                 # Declarative base
  models/
    user.py
    group.py
    expense.py
    settlement.py
    notification.py
    audit.py
  repositories/
    base.py                 # Generic CRUD base
    user_repository.py
    group_repository.py
    expense_repository.py
    settlement_repository.py
    notification_repository.py
  services/
    auth_service.py
    user_service.py
    group_service.py
    expense_service.py
    balance_service.py
    settlement_service.py
    notification_service.py
  schemas/
    auth.py
    users.py
    groups.py
    expenses.py
    settlements.py
    balances.py
    notifications.py
    errors.py               # RFC 7807 ProblemDetail schema
  templates/
    base.html
    auth/
    dashboard/
    groups/
    expenses/
    settlements/
  static/
    css/
    js/
  utils/
    decimal_utils.py        # Decimal rounding, remainder distribution
    pagination.py
    cache_keys.py           # Cache key namespace helpers
tests/
  unit/
  integration/
  property/
migrations/
  versions/
  env.py
  alembic.ini
```

---

## Components and Interfaces

### Auth Service

Responsible for JWT lifecycle and credential verification.

```python
class AuthService:
    async def register(self, data: RegisterRequest) -> UserPublic
    async def login(self, data: LoginRequest) -> TokenPair
    async def refresh_token(self, refresh_token: str) -> AccessToken
    async def logout(self, user_id: UUID, refresh_token: str) -> None
    async def get_current_user(self, token: str) -> User
```

**JWT Strategy**: Access tokens expire in 15 minutes; refresh tokens expire in 7 days. Refresh tokens are stored in the `refresh_tokens` table (hashed) so they can be invalidated on logout. On logout, the refresh token row is deleted.

### User Service

```python
class UserService:
    async def get_profile(self, user_id: UUID) -> UserPublic
    async def update_profile(self, user_id: UUID, data: UpdateProfileRequest) -> UserPublic
    async def upload_avatar(self, user_id: UUID, file: UploadFile) -> UserPublic
```

Avatar files are stored on disk (or object storage in production) and the URL is persisted in the `users` table.

### Group Service

```python
class GroupService:
    async def create_group(self, creator_id: UUID, data: CreateGroupRequest) -> GroupDetail
    async def add_member(self, admin_id: UUID, group_id: UUID, email: str) -> MemberList
    async def remove_member(self, admin_id: UUID, group_id: UUID, member_id: UUID) -> None
    async def update_group(self, admin_id: UUID, group_id: UUID, data: UpdateGroupRequest) -> GroupDetail
    async def delete_group(self, admin_id: UUID, group_id: UUID) -> None
    async def list_user_groups(self, user_id: UUID) -> list[GroupSummary]
    async def get_group(self, user_id: UUID, group_id: UUID) -> GroupDetail
```

### Expense Service

```python
class ExpenseService:
    async def create_expense(self, user_id: UUID, group_id: UUID, data: CreateExpenseRequest) -> ExpenseDetail
    async def update_expense(self, user_id: UUID, expense_id: UUID, data: UpdateExpenseRequest) -> ExpenseDetail
    async def delete_expense(self, user_id: UUID, expense_id: UUID) -> None
    async def get_expense(self, user_id: UUID, expense_id: UUID) -> ExpenseDetail
    async def list_expenses(self, user_id: UUID, group_id: UUID, filters: ExpenseFilters, page: int) -> Page[ExpenseDetail]
    async def search_expenses(self, user_id: UUID, group_id: UUID, keyword: str, page: int) -> Page[ExpenseDetail]
```

### Balance Service

```python
class BalanceService:
    async def get_group_balances(self, user_id: UUID, group_id: UUID) -> list[MemberBalance]
    async def get_user_overall_balances(self, user_id: UUID) -> list[CounterpartyBalance]
    async def get_simplified_debts(self, user_id: UUID, group_id: UUID) -> list[Debt]
    async def invalidate_group_cache(self, group_id: UUID) -> None
```

**Debt Simplification Algorithm** (greedy min-cash-flow):
1. Compute net balance for each member.
2. Separate into creditors (positive balance) and debtors (negative balance).
3. Use a max-heap for creditors and min-heap for debtors.
4. Repeatedly match the largest creditor with the largest debtor, creating one `Debt` record per iteration, until all balances reach zero.
5. This produces at most `n-1` transactions for `n` members.

### Settlement Service

```python
class SettlementService:
    async def create_settlement(self, user_id: UUID, group_id: UUID, data: CreateSettlementRequest) -> SettlementDetail
    async def delete_settlement(self, user_id: UUID, settlement_id: UUID) -> None
    async def list_settlements(self, user_id: UUID, group_id: UUID, page: int) -> Page[SettlementDetail]
```

### Notification Service

```python
class NotificationService:
    async def get_activity_feed(self, user_id: UUID) -> list[ActivityEvent]
    async def mark_feed_read(self, user_id: UUID) -> None
    async def get_unread_count(self, user_id: UUID) -> int
    async def create_expense_event(self, expense: Expense, event_type: EventType) -> None
    async def create_settlement_event(self, settlement: Settlement, event_type: EventType) -> None
```

### Split Strategy

Split calculation is isolated in `utils/decimal_utils.py` and called by `ExpenseService`:

```python
def compute_equal_splits(total: Decimal, participants: list[UUID]) -> dict[UUID, Decimal]
def compute_exact_splits(splits: list[SplitInput]) -> dict[UUID, Decimal]
def compute_percentage_splits(total: Decimal, splits: list[PercentageSplitInput]) -> dict[UUID, Decimal]
```

Remainder distribution: when `total / n` produces a repeating decimal, the remainder (computed as `total - sum(truncated_splits)`) is added to the first participant's share. This guarantees `sum(splits) == total` exactly.

### API Dependency Injection

```python
# app/api/v1/dependencies.py
async def get_db() -> AsyncSession          # yields DB session
async def get_cache() -> Redis              # yields Redis client
async def get_current_user(token: str = Depends(oauth2_scheme), db = Depends(get_db)) -> User
async def require_group_member(group_id: UUID, current_user = Depends(get_current_user), ...) -> GroupMembership
async def require_group_admin(membership = Depends(require_group_member)) -> GroupMembership
```

---

## Data Models

### Entity Relationship Diagram

```mermaid
erDiagram
    users {
        UUID id PK
        VARCHAR name
        VARCHAR email UK
        VARCHAR password_hash
        VARCHAR avatar_url
        TIMESTAMP created_at
        TIMESTAMP updated_at
        BOOLEAN is_active
    }
    refresh_tokens {
        UUID id PK
        UUID user_id FK
        VARCHAR token_hash UK
        TIMESTAMP expires_at
        TIMESTAMP created_at
    }
    groups {
        UUID id PK
        VARCHAR name
        TEXT description
        TIMESTAMP created_at
        TIMESTAMP updated_at
        BOOLEAN is_deleted
        TIMESTAMP deleted_at
    }
    group_members {
        UUID id PK
        UUID group_id FK
        UUID user_id FK
        VARCHAR role
        TIMESTAMP joined_at
    }
    expenses {
        UUID id PK
        UUID group_id FK
        UUID payer_id FK
        VARCHAR description
        DECIMAL amount
        VARCHAR split_strategy
        DATE expense_date
        TIMESTAMP created_at
        TIMESTAMP updated_at
        BOOLEAN is_deleted
        TIMESTAMP deleted_at
        UUID created_by FK
    }
    expense_splits {
        UUID id PK
        UUID expense_id FK
        UUID user_id FK
        DECIMAL amount
        DECIMAL percentage
    }
    settlements {
        UUID id PK
        UUID group_id FK
        UUID payer_id FK
        UUID payee_id FK
        DECIMAL amount
        DATE settlement_date
        TIMESTAMP created_at
        BOOLEAN is_deleted
        TIMESTAMP deleted_at
    }
    notifications {
        UUID id PK
        UUID user_id FK
        VARCHAR event_type
        UUID group_id FK
        UUID actor_id FK
        JSONB payload
        BOOLEAN is_read
        TIMESTAMP created_at
    }
    audit_logs {
        UUID id PK
        VARCHAR entity_type
        UUID entity_id
        UUID actor_id FK
        VARCHAR action
        JSONB previous_values
        TIMESTAMP created_at
    }

    users ||--o{ refresh_tokens : "has"
    users ||--o{ group_members : "belongs to"
    groups ||--o{ group_members : "has"
    groups ||--o{ expenses : "contains"
    groups ||--o{ settlements : "contains"
    users ||--o{ expenses : "pays"
    expenses ||--o{ expense_splits : "split into"
    users ||--o{ expense_splits : "owes"
    users ||--o{ settlements : "pays"
    users ||--o{ settlements : "receives"
    users ||--o{ notifications : "receives"
    users ||--o{ audit_logs : "performs"
```

### SQLAlchemy Models (key fields)

**User**
```python
class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    is_active: Mapped[bool] = mapped_column(default=True)
```

**Group**
```python
class Group(Base):
    __tablename__ = "groups"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    is_deleted: Mapped[bool] = mapped_column(default=False)
    deleted_at: Mapped[datetime | None]
```

**GroupMember**
```python
class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # "admin" | "member"
    joined_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

**Expense**
```python
class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_expense_positive_amount"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id"), nullable=False)
    payer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=19, scale=4), nullable=False)
    split_strategy: Mapped[str] = mapped_column(String(20), nullable=False)  # "equal"|"exact"|"percentage"
    expense_date: Mapped[date] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    is_deleted: Mapped[bool] = mapped_column(default=False)
    deleted_at: Mapped[datetime | None]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
```

**ExpenseSplit**
```python
class ExpenseSplit(Base):
    __tablename__ = "expense_splits"
    __table_args__ = (CheckConstraint("amount >= 0", name="ck_split_non_negative"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    expense_id: Mapped[UUID] = mapped_column(ForeignKey("expenses.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=19, scale=4), nullable=False)
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(precision=7, scale=4))
```

**Settlement**
```python
class Settlement(Base):
    __tablename__ = "settlements"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_settlement_positive_amount"),
        CheckConstraint("payer_id != payee_id", name="ck_settlement_different_users"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id"), nullable=False)
    payer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    payee_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=19, scale=4), nullable=False)
    settlement_date: Mapped[date] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    is_deleted: Mapped[bool] = mapped_column(default=False)
    deleted_at: Mapped[datetime | None]
```

**Notification**
```python
class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    group_id: Mapped[UUID | None] = mapped_column(ForeignKey("groups.id"))
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_read: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
```

**AuditLog**
```python
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(nullable=False)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # "create"|"update"|"delete"
    previous_values: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

### Pydantic Schemas (key examples)

```python
# schemas/expenses.py
class SplitInput(BaseModel):
    user_id: UUID
    amount: Decimal

class PercentageSplitInput(BaseModel):
    user_id: UUID
    percentage: Decimal

class CreateExpenseRequest(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    amount: Decimal = Field(gt=0)
    payer_id: UUID
    expense_date: date
    split_strategy: Literal["equal", "exact", "percentage"]
    participants: list[UUID] = Field(min_length=1)          # for "equal"
    splits: list[SplitInput] | None = None                  # for "exact"
    percentage_splits: list[PercentageSplitInput] | None = None  # for "percentage"

# schemas/errors.py
class ProblemDetail(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    instance: str
```

### Cache Key Schema

All cache keys follow the format `{entity}:{id}:{operation}`:

| Key Pattern | TTL | Invalidated By |
|---|---|---|
| `balance:group:{group_id}:members` | 300s | expense/settlement create/update/delete |
| `balance:group:{group_id}:simplified` | 300s | expense/settlement create/update/delete |
| `balance:user:{user_id}:overall` | 300s | expense/settlement create/update/delete |

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*


### Property 1: Registration Input Validation

*For any* registration request where the password has fewer than 8 characters or the email is malformed, the User_Service SHALL reject the request with a 422 error and the user record SHALL NOT be created.

**Validates: Requirements 1.3, 1.4**

### Property 2: Password Hashing

*For any* successful user registration with a given plaintext password, the stored `password_hash` SHALL NOT equal the plaintext password, and `bcrypt.verify(plaintext, stored_hash)` SHALL return `True`.

**Validates: Requirements 1.5**

### Property 3: Token Pair on Login

*For any* registered user with valid credentials, a login request SHALL return an access token with a 15-minute expiry claim and a refresh token with a 7-day expiry claim.

**Validates: Requirements 2.1**

### Property 4: Wrong Credentials Rejected

*For any* registered user, a login request with an incorrect password SHALL return a 401 Unauthorized response.

**Validates: Requirements 2.2**

### Property 5: Refresh Token Round Trip

*For any* valid, unexpired refresh token obtained from a login, using it to request a new access token SHALL succeed and return a valid access token; after logout, using the same refresh token SHALL return a 401 Unauthorized response.

**Validates: Requirements 2.4, 2.6**

### Property 6: Protected Endpoint Access Control

*For any* protected endpoint, a request with a valid access token SHALL be permitted (non-401 response), and a request with no token or an expired token SHALL return a 401 Unauthorized response.

**Validates: Requirements 2.7, 2.8**

### Property 7: Profile Fields Completeness

*For any* registered user, requesting their own profile SHALL return a response containing all required fields: `id`, `name`, `email`, `avatar_url`, and `created_at`.

**Validates: Requirements 3.1**

### Property 8: Profile Update Round Trip

*For any* authenticated user and any valid new name string, submitting a profile update SHALL result in the returned profile containing the new name, and a subsequent profile fetch SHALL also return the new name.

**Validates: Requirements 3.2**

### Property 9: Cross-User Profile Protection

*For any* two distinct authenticated users A and B, user A's attempt to update user B's profile SHALL return a 403 Forbidden response.

**Validates: Requirements 3.5**

### Property 10: Group Creation Invariants

*For any* authenticated user creating a group with a valid name, the group SHALL be created with the creator as a member with the "admin" role, and the response SHALL contain the group details with a 201 status.

**Validates: Requirements 4.1**

### Property 11: Group Membership Management

*For any* group admin adding a registered user to a group, the user SHALL appear in the group's member list with the "member" role; for any non-admin member attempting an admin-only operation, the response SHALL be 403 Forbidden.

**Validates: Requirements 4.2, 4.9**

### Property 12: Group Update Round Trip

*For any* group admin and any valid new group name or description, submitting a group update SHALL result in the returned group containing the new values, and a subsequent group fetch SHALL also return the updated values.

**Validates: Requirements 4.5**

### Property 13: Group Listing Completeness

*For any* authenticated user who is a member of N active groups, requesting their group list SHALL return exactly those N active groups, each including member count and total outstanding balance.

**Validates: Requirements 4.8**

### Property 14: Expense Creation Persists All Data

*For any* valid expense creation request (positive amount, valid payer, splits summing to total, all participants are group members), the expense SHALL be persisted with all splits, and a subsequent fetch by id SHALL return all splits with correct amounts.

**Validates: Requirements 5.1, 5.6**

### Property 15: Split Validation Rejects Invalid Inputs

*For any* expense creation request where the expense amount is zero or negative, OR where any split participant is not a group member, OR where the sum of splits deviates from the total by more than 0.01, the Expense_Service SHALL return a 422 Unprocessable Entity error and no expense SHALL be persisted.

**Validates: Requirements 5.2, 5.3, 5.4**

### Property 16: Expense List Ordering

*For any* group with N expenses, requesting the expense list SHALL return expenses in reverse chronological order (newest first), with each page containing at most 20 items.

**Validates: Requirements 5.5**

### Property 17: Split Strategies Produce Exact Totals

*For any* expense total and any set of participants, the "equal" split strategy SHALL produce split amounts that sum exactly to the total (using Decimal arithmetic, with any remainder assigned to the first participant); the "percentage" split strategy SHALL produce split amounts that sum exactly to the total when percentages sum to 100 (with any Decimal remainder assigned to the first participant).

**Validates: Requirements 5.7, 6.1, 6.3**

### Property 18: Exact Split Round Trip

*For any* set of explicitly provided Decimal split amounts that sum to the expense total, the "exact" split strategy SHALL store each participant's amount exactly as provided, and a subsequent fetch SHALL return the same amounts.

**Validates: Requirements 6.2**

### Property 19: Split Strategy Validation

*For any* "percentage" split where the percentages do not sum to 100, OR any "exact" split where the amounts do not sum to the expense total within 0.01, the Expense_Service SHALL return a 422 Unprocessable Entity error.

**Validates: Requirements 6.4, 6.5**

### Property 20: Split Strategy Recorded

*For any* expense created with a given split strategy ("equal", "exact", or "percentage"), the strategy field SHALL be persisted and returned on subsequent fetches of that expense.

**Validates: Requirements 6.6**

### Property 21: Expense Edit Authorization

*For any* expense, a non-admin, non-payer group member's attempt to edit or delete the expense SHALL return a 403 Forbidden response.

**Validates: Requirements 7.3**

### Property 22: Expense Audit Trail

*For any* expense that is edited or deleted, an audit log entry SHALL be created containing the actor's id, the timestamp, and the previous values of the changed fields.

**Validates: Requirements 7.4**

### Property 23: Balance Deletion Reversal

*For any* expense or settlement that is created and then deleted, the group balances after deletion SHALL equal the group balances that existed before the expense or settlement was created.

**Validates: Requirements 7.2, 10.5**

### Property 24: Group Balance Correctness

*For any* group with any combination of non-deleted expenses and settlements, the Balance_Service SHALL return each member's net balance equal to the mathematical sum of: (amounts paid by that member) − (split amounts owed by that member) + (settlements received) − (settlements paid), computed using Decimal arithmetic.

**Validates: Requirements 8.1, 8.3**

### Property 25: Overall Balance Aggregation

*For any* user who is a member of multiple groups, the overall balance per counterparty SHALL equal the sum of that user's net balance with that counterparty across all groups.

**Validates: Requirements 8.2**

### Property 26: Cache Invalidation on Mutation

*For any* expense or settlement creation, update, or deletion, the Cache entries for all affected groups and users SHALL be invalidated, such that the next balance request returns freshly computed values reflecting the mutation.

**Validates: Requirements 8.5, 9.4**

### Property 27: Debt Simplification Correctness

*For any* group balance state with N members, the simplified debt set SHALL satisfy two invariants: (1) applying all simplified debts results in all member balances reaching zero (equivalence), and (2) the number of simplified debts is at most N−1 (minimality).

**Validates: Requirements 9.1, 9.2**

### Property 28: Settlement Validation

*For any* settlement creation request where the amount is zero or negative, the Settlement_Service SHALL return a 422 Unprocessable Entity error and no settlement SHALL be persisted.

**Validates: Requirements 10.2**

### Property 29: Settlement List Ordering

*For any* group with N settlements, requesting the settlement history SHALL return settlements in reverse chronological order (newest first), with each page containing at most 20 items.

**Validates: Requirements 10.4**

### Property 30: Activity Feed Ordering and Limit

*For any* user with activity events across their groups, the activity feed SHALL return at most 50 events ordered by timestamp descending, and after viewing the feed all returned events SHALL be marked as read with the unread count reflecting only events not yet viewed.

**Validates: Requirements 11.1, 11.4**

### Property 31: Activity Event Fan-Out

*For any* expense creation, edit, or deletion in a group with M members, M notification records SHALL be created (one per member); for any settlement creation or deletion, exactly 2 notification records SHALL be created (one for payer, one for payee).

**Validates: Requirements 11.2, 11.3**

### Property 32: Search and Filter Correctness

*For any* combination of search/filter parameters (keyword, date range, payer id), all returned expenses SHALL satisfy every specified filter condition (keyword match is case-insensitive substring; date is within range; payer matches), and no expense failing any condition SHALL appear in the results.

**Validates: Requirements 12.1, 12.2, 12.3, 12.4**

### Property 33: Request ID Propagation

*For any* HTTP request, the response SHALL contain an `X-Request-ID` header; if the request included an `X-Request-ID` header, the response SHALL echo the same value; if absent, the response SHALL contain a newly generated UUID v4.

**Validates: Requirements 13.4**

### Property 34: RFC 7807 Error Format

*For any* request that results in an error response (4xx or 5xx), the response body SHALL be a valid RFC 7807 Problem Details JSON object containing all required fields: `type`, `title`, `status`, `detail`, and `instance`.

**Validates: Requirements 13.5**

### Property 35: XSS Input Sanitization

*For any* user-supplied string input containing HTML special characters or script tags, the stored and rendered value SHALL have HTML entities escaped such that no executable script content is present.

**Validates: Requirements 17.5**

### Property 36: JWT Tamper Rejection

*For any* JWT token whose payload or signature has been modified after issuance, the Auth_Service SHALL reject the token and return a 401 Unauthorized response.

**Validates: Requirements 17.6**

---

## Error Handling

### Error Response Format

All errors return RFC 7807 Problem Details:

```json
{
  "type": "https://api.expenseshare.example/errors/validation-error",
  "title": "Unprocessable Entity",
  "status": 422,
  "detail": "Split amounts do not sum to expense total",
  "instance": "/api/v1/groups/abc/expenses"
}
```

### Exception Hierarchy

```python
# app/core/exceptions.py
class AppException(Exception):
    status_code: int
    error_type: str
    title: str

class NotFoundError(AppException):        # 404
class ConflictError(AppException):        # 409
class ForbiddenError(AppException):       # 403
class UnauthorizedError(AppException):    # 401
class ValidationError(AppException):     # 422
class RateLimitError(AppException):       # 429
```

A global FastAPI exception handler converts `AppException` subclasses to RFC 7807 responses. Unhandled exceptions are caught by a catch-all handler that logs the full stack trace and returns a 500 with a generic Problem Details body.

### Service-Level Error Handling

| Scenario | Exception | HTTP Status |
|---|---|---|
| Resource not found | `NotFoundError` | 404 |
| Duplicate email on registration | `ConflictError` | 409 |
| Remove member with non-zero balance | `ConflictError` | 409 |
| Delete group with outstanding debts | `ConflictError` | 409 |
| Non-admin performing admin operation | `ForbiddenError` | 403 |
| Non-payer editing expense | `ForbiddenError` | 403 |
| Invalid JWT / expired token | `UnauthorizedError` | 401 |
| Split sum mismatch | `ValidationError` | 422 |
| Negative/zero amount | `ValidationError` | 422 |
| Avatar file too large / wrong type | `ValidationError` | 422 |
| Rate limit exceeded | `RateLimitError` | 429 |

### Cache Failure Handling

Redis failures are caught at the `BalanceService` level. On `RedisError`, the service logs a `WARNING`-level structured event and falls through to the database computation path. The client receives a correct response with no indication of the cache failure.

### Transaction Rollback

All write operations use `async with db.begin():` context managers. Any exception raised within the block triggers an automatic rollback. The exception propagates up to the route handler, which converts it to an appropriate HTTP error response.

---

## Testing Strategy

### Overview

The testing strategy uses a dual approach: **property-based tests** for universal correctness properties and **example-based unit/integration tests** for specific scenarios, edge cases, and infrastructure behavior.

### Property-Based Testing

**Library**: [Hypothesis](https://hypothesis.readthedocs.io/) for Python.

**Configuration**: Each property test runs a minimum of 100 examples (`@settings(max_examples=100)`).

**Tag format**: Each property test is tagged with a comment:
```python
# Feature: expense-sharing-app, Property N: <property_text>
```

**Scope**: Properties 1–36 above are each implemented as a single Hypothesis property test. Database interactions use an in-memory SQLite or a test PostgreSQL instance; Redis is mocked using `fakeredis`.

**Key Hypothesis strategies**:
```python
# Custom strategies for domain objects
from hypothesis import strategies as st

valid_email = st.emails()
valid_password = st.text(min_size=8, max_size=64)
positive_decimal = st.decimals(min_value="0.01", max_value="99999.99", places=2)
split_strategy = st.sampled_from(["equal", "exact", "percentage"])
```

### Unit Tests

Located in `tests/unit/`. Focus on:
- Split calculation functions in `utils/decimal_utils.py` (exact arithmetic verification)
- JWT encode/decode in `core/security.py`
- Cache key generation in `utils/cache_keys.py`
- Debt simplification algorithm in `balance_service.py`
- Pydantic schema validation edge cases

### Integration Tests

Located in `tests/integration/`. Use a real PostgreSQL test database and `fakeredis`. Focus on:
- Full request/response cycles via FastAPI `TestClient`
- Transaction atomicity (simulate mid-transaction failures)
- Cache hit/miss behavior
- Concurrent balance modification (race condition tests)
- Health endpoint with DB/Redis up and down

### Smoke Tests

Located in `tests/smoke/`. Verify:
- All API endpoints accessible under `/api/v1/`
- OpenAPI schema served at `/api/v1/openapi.json`
- Alembic migration scripts have both `upgrade()` and `downgrade()`
- Database constraints (FK, check constraints, unique indexes) present in schema
- JWT algorithm and secret key length configuration
- Cache key naming convention

### Test Structure

```
tests/
  unit/
    test_decimal_utils.py
    test_security.py
    test_debt_simplification.py
    test_cache_keys.py
    test_schemas.py
  integration/
    test_auth.py
    test_users.py
    test_groups.py
    test_expenses.py
    test_balances.py
    test_settlements.py
    test_notifications.py
    test_health.py
    test_transactions.py
  property/
    test_registration_properties.py
    test_auth_properties.py
    test_expense_properties.py
    test_balance_properties.py
    test_settlement_properties.py
    test_search_properties.py
    test_api_properties.py
  smoke/
    test_routes.py
    test_schema.py
    test_migrations.py
  conftest.py
```

### Test Configuration

```python
# conftest.py
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import fakeredis.aioredis

@pytest.fixture
async def db_session():
    engine = create_async_engine("postgresql+asyncpg://test:test@localhost/test_db")
    async with AsyncSession(engine) as session:
        yield session
        await session.rollback()

@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()

@pytest.fixture
async def client(db_session, fake_redis):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_cache] = lambda: fake_redis
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
```
