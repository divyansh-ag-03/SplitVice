# SplitVice

A production-style expense sharing application inspired by Splitwise, built with a backend-first architecture using FastAPI, HTMX, PostgreSQL, and async SQLAlchemy.

SplitVice focuses on:
- financial correctness
- maintainable architecture
- server-rendered simplicity
- fast iteration
- pragmatic engineering over overengineering

---

## Features

### Authentication
- JWT access + refresh tokens
- Secure HttpOnly cookie auth for web UI
- Bearer token auth for API usage
- Password hashing with bcrypt
- Refresh token invalidation on logout

### Groups
- Create and manage groups
- Admin/member roles
- Add/remove members
- Leave group protections
- Group balance summaries

### Expenses
- Exact split expense tracking
- Equal split generation
- Live split validation
- Edit/delete expenses
- Soft delete support
- Atomic expense + split transactions

### Balances
- Dynamic balance computation
- Participant-aware expense handling
- Simplified debt calculation
- “Who pays whom” settlement suggestions
- Exact Decimal-based accounting
- Balances always sum to zero

### Settlements
- Record repayments
- Pairwise debt validation
- Settlement reversal via soft delete
- Automatic balance recomputation

### Web UI
- Server-rendered frontend
- HTMX-enhanced interactions
- TailwindCSS styling
- Responsive layout
- Dashboard + group pages

### Production Features
- Dockerized deployment
- PostgreSQL + Alembic migrations
- Structured logging
- Security headers middleware
- Optional Sentry integration
- Health checks
- 169 integration tests

---

# Tech Stack

## Backend
- Python
- FastAPI
- SQLAlchemy 2.0 Async
- Alembic
- PostgreSQL
- Redis (minimal MVP use)

## Frontend
- HTMX
- Jinja2 Templates
- TailwindCSS

## Infrastructure
- Docker
- Docker Compose
- Railway / Render deployment ready

## Testing
- pytest
- async integration tests
- SQLite in-memory isolated test DB

---

# Architecture Philosophy

SplitVice intentionally avoids:
- microservices
- CQRS
- event buses
- websocket complexity
- frontend SPA complexity
- enterprise abstraction layers

The project is designed around:
- modular monolith architecture
- explicit business logic
- maintainability
- readability
- solo developer productivity

---

# Project Structure

```text
.
├── app/
│   ├── api/
│   ├── core/
│   ├── db/
│   ├── models/
│   ├── repositories/
│   ├── schemas/
│   ├── services/
│   ├── web/
│   ├── templates/
│   ├── static/
│   └── main.py
├── migrations/
├── tests/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

---

# Core Financial Model

SplitVice computes balances dynamically from:
- expenses
- expense splits
- settlements

No balances are stored directly.

For every expense:

```text
net balance =
amount paid
-
amount owed
```

Only users present in `expense_splits` participate in an expense.

This ensures:
- participant-aware accounting
- correct partial participation handling
- accurate debt simplification

All money calculations use Python `Decimal`.

No floats are used anywhere in financial computation.

---

# Example Balance Flow

Group:
- Alice
- Bob
- Charlie
- David

Expense 1:
- Alice pays ₹400
- split equally among all 4

Result:
- Alice +300
- Bob -100
- Charlie -100
- David -100

Expense 2:
- Bob pays ₹300
- split only among Bob, Charlie, David

Result:
- Alice unaffected
- Bob +200
- Charlie -100
- David -100

Final:
- Alice +300
- Bob +100
- Charlie -200
- David -200

Balances always sum to zero.

---

# Running Locally

## 1. Clone the repo

```bash
git clone <your-repo-url>
cd splitvice
```

---

## 2. Create environment file

```bash
cp .env.example .env
```

Generate a JWT secret:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 3. Install dependencies

```bash
pip install -e ".[dev]"
```

---

## 4. Start PostgreSQL

```bash
docker compose up db -d
```

---

## 5. Run migrations

```bash
alembic upgrade head
```

---

## 6. Start the app

```bash
uvicorn app.main:app --reload
```

---

# Docker Run

```bash
docker compose up
```

App:
```text
http://localhost:8000
```

Swagger:
```text
http://localhost:8000/api/v1/docs
```

Health:
```text
http://localhost:8000/health
```

---

# Running Tests

```bash
python -m pytest tests/ -v
```

Tests use:
- isolated SQLite in-memory DB
- async test setup
- independent schema per test

Current coverage:
- 169 integration tests
- zero warnings

---

# API Documentation

Interactive Swagger UI:

```text
/api/v1/docs
```

OpenAPI schema:

```text
/api/v1/openapi.json
```

---

# Environment Variables

| Variable | Description |
|---|---|
| JWT_SECRET | JWT signing secret |
| DATABASE_URL | PostgreSQL connection string |
| ENV | development / production |
| DEBUG | Enable debug logging |
| ACCESS_TOKEN_EXPIRE_MINUTES | Access token lifetime |
| REFRESH_TOKEN_EXPIRE_DAYS | Refresh token lifetime |
| SENTRY_DSN | Optional Sentry integration |
| ALLOWED_HOSTS | Trusted production hosts |

---

# Production Features

- Secure cookies in production
- Structured JSON logging
- Security headers middleware
- Health checks
- Dockerized deployment
- Sentry support
- Trusted host support

---

# Deployment

SplitVice is designed for simple monolith deployment.

Recommended platforms:
- Railway
- Render

The app deploys as:
- one FastAPI service
- one PostgreSQL database

No separate frontend deployment required.

---

# Future Improvements (v2)

Planned but intentionally deferred:

- Redis balance caching
- Notifications/activity feed
- Expense search/filtering
- Avatar uploads
- CSV export
- Audit logs
- Rate limiting
- Additional security hardening

---

# Design Principles

This project prioritizes:

- shipping speed
- maintainability
- correctness
- simplicity
- explicit logic
- backend-first architecture

Over:

- architectural purity
- premature optimization
- enterprise patterns
- abstraction-heavy design

---

# Screenshots

_Add screenshots here once deployed._

Suggested:
- Dashboard
- Group detail page
- Expense form
- Balances page
- Settlement flow

---

# Author

Built by Divyansh.

Inspired by Splitwise, rebuilt with a pragmatic Python-first architecture focused on correctness and maintainability.
