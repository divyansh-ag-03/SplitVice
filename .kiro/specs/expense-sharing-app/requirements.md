# Requirements Document

## Introduction

A production-grade expense sharing application inspired by Splitwise. The system allows users to create groups, record shared expenses, split costs among participants using multiple strategies, and track who owes whom. It exposes a REST API consumed by an HTMX/Jinja2 frontend and is designed for future mobile app integration. All monetary calculations use `Decimal` arithmetic to guarantee precision.

---

## Glossary

- **User**: An authenticated person with an account in the system.
- **Group**: A named collection of Users who share expenses together.
- **Expense**: A monetary transaction paid by one or more Users on behalf of a Group.
- **Split**: The portion of an Expense owed by a specific User.
- **Settlement**: A payment made by one User to another to reduce or eliminate a debt.
- **Balance**: The net amount a User owes or is owed within a Group or across all Groups.
- **Debt**: A directional relationship indicating User A owes User B a specific Decimal amount.
- **Simplification**: The process of reducing multiple Debts into a minimal set of Settlements.
- **Auth_Service**: The component responsible for user authentication and JWT management.
- **User_Service**: The component responsible for user account management.
- **Group_Service**: The component responsible for group lifecycle management.
- **Expense_Service**: The component responsible for recording and managing expenses.
- **Balance_Service**: The component responsible for computing and caching balances and debts.
- **Settlement_Service**: The component responsible for recording and applying settlements.
- **Notification_Service**: The component responsible for in-app activity notifications.
- **Cache**: The Redis-backed caching layer.
- **Repository**: The data-access layer that mediates between services and the database.
- **JWT**: JSON Web Token used for stateless authentication.
- **Access_Token**: A short-lived JWT granting API access.
- **Refresh_Token**: A long-lived token used to obtain a new Access_Token.
- **Decimal**: Python `decimal.Decimal` type used for all monetary values.
- **EARS**: Easy Approach to Requirements Syntax.

---

## Requirements

---

### Requirement 1: User Registration

**User Story:** As a new visitor, I want to create an account with my name, email, and password, so that I can start tracking shared expenses.

#### Acceptance Criteria

1. WHEN a registration request is received with a unique email, valid name, and password of at least 8 characters, THE User_Service SHALL create a new User record and return a 201 response containing the created user's public profile.
2. WHEN a registration request is received with an email that already exists in the system, THE User_Service SHALL return a 409 Conflict error with a descriptive message.
3. WHEN a registration request is received with a password shorter than 8 characters, THE User_Service SHALL return a 422 Unprocessable Entity error listing the violated constraint.
4. WHEN a registration request is received with a malformed email address, THE User_Service SHALL return a 422 Unprocessable Entity error.
5. THE User_Service SHALL store passwords as bcrypt hashes and SHALL NOT store plaintext passwords.

---

### Requirement 2: User Authentication

**User Story:** As a registered user, I want to log in with my email and password, so that I can access my account securely.

#### Acceptance Criteria

1. WHEN a login request is received with a valid email and correct password, THE Auth_Service SHALL return an Access_Token with a 15-minute expiry and a Refresh_Token with a 7-day expiry.
2. WHEN a login request is received with a valid email and incorrect password, THE Auth_Service SHALL return a 401 Unauthorized error.
3. WHEN a login request is received with an email that does not exist, THE Auth_Service SHALL return a 401 Unauthorized error.
4. WHEN a token refresh request is received with a valid, unexpired Refresh_Token, THE Auth_Service SHALL return a new Access_Token.
5. WHEN a token refresh request is received with an expired or invalid Refresh_Token, THE Auth_Service SHALL return a 401 Unauthorized error.
6. WHEN a logout request is received with a valid Access_Token, THE Auth_Service SHALL invalidate the associated Refresh_Token so it cannot be reused.
7. WHILE a request carries a valid Access_Token, THE Auth_Service SHALL allow access to protected endpoints.
8. IF a request to a protected endpoint carries no token or an expired token, THEN THE Auth_Service SHALL return a 401 Unauthorized error.

---

### Requirement 3: User Profile Management

**User Story:** As an authenticated user, I want to view and update my profile, so that my name and avatar are accurate.

#### Acceptance Criteria

1. WHEN an authenticated user requests their own profile, THE User_Service SHALL return the user's id, name, email, avatar URL, and account creation timestamp.
2. WHEN an authenticated user submits a profile update with a new name, THE User_Service SHALL persist the change and return the updated profile.
3. WHEN an authenticated user submits an avatar upload of a JPEG or PNG file not exceeding 5 MB, THE User_Service SHALL store the file and update the user's avatar URL.
4. IF an avatar upload exceeds 5 MB or is not a JPEG or PNG file, THEN THE User_Service SHALL return a 422 Unprocessable Entity error.
5. THE User_Service SHALL prevent a user from modifying another user's profile, returning a 403 Forbidden error when such an attempt is made.

---

### Requirement 4: Group Management

**User Story:** As an authenticated user, I want to create and manage groups, so that I can organize expenses with specific sets of people.

#### Acceptance Criteria

1. WHEN an authenticated user creates a group with a unique name and optional description, THE Group_Service SHALL create the group, add the creator as a member with the "admin" role, and return a 201 response with the group details.
2. WHEN an authenticated user who is a group admin adds another registered user to the group by email, THE Group_Service SHALL add that user as a member with the "member" role and return the updated member list.
3. WHEN an authenticated user who is a group admin removes a member who has a non-zero Balance in the group, THE Group_Service SHALL return a 409 Conflict error indicating the balance must be settled first.
4. WHEN an authenticated user who is a group admin removes a member with a zero Balance, THE Group_Service SHALL remove the member and return a 200 response.
5. WHEN an authenticated user who is a group admin updates the group name or description, THE Group_Service SHALL persist the changes and return the updated group.
6. WHEN an authenticated user who is a group admin deletes a group that has no outstanding Debts, THE Group_Service SHALL soft-delete the group and return a 200 response.
7. IF a group deletion is attempted while outstanding Debts exist, THEN THE Group_Service SHALL return a 409 Conflict error.
8. WHEN an authenticated user requests the list of groups they belong to, THE Group_Service SHALL return all active groups for that user including each group's member count and total outstanding balance.
9. THE Group_Service SHALL prevent non-admin members from performing admin-only operations, returning a 403 Forbidden error.

---

### Requirement 5: Expense Recording

**User Story:** As a group member, I want to record an expense paid by one person, so that the cost is tracked and split among the relevant members.

#### Acceptance Criteria

1. WHEN a group member submits an expense with a description, a positive Decimal amount, a payer (who must be a group member), a date, and a list of participant Splits that sum to the total amount, THE Expense_Service SHALL persist the expense and all Splits, update affected Balances, invalidate the relevant Cache entries, and return a 201 response with the full expense detail.
2. IF the sum of submitted Splits does not equal the expense amount within a tolerance of 0.01 currency units, THEN THE Expense_Service SHALL return a 422 Unprocessable Entity error.
3. IF any participant in the Splits is not a member of the group, THEN THE Expense_Service SHALL return a 422 Unprocessable Entity error.
4. IF the expense amount is zero or negative, THEN THE Expense_Service SHALL return a 422 Unprocessable Entity error.
5. WHEN a group member requests the expense list for a group, THE Expense_Service SHALL return expenses in reverse chronological order, paginated at 20 items per page, including payer name, amount, description, date, and split summary.
6. WHEN a group member requests a single expense by id, THE Expense_Service SHALL return the full expense detail including all Splits with participant names and amounts.
7. THE Expense_Service SHALL perform all Split amount calculations using Decimal arithmetic and SHALL NOT use floating-point arithmetic.

---

### Requirement 6: Expense Split Strategies

**User Story:** As a group member, I want to split expenses equally, by exact amounts, or by percentage, so that I can handle different real-world cost-sharing scenarios.

#### Acceptance Criteria

1. WHEN an expense is created with split strategy "equal", THE Expense_Service SHALL divide the total amount equally among all specified participants, distributing any remainder of Decimal division to the first participant, such that all Splits sum exactly to the total.
2. WHEN an expense is created with split strategy "exact", THE Expense_Service SHALL use the explicitly provided Decimal amount for each participant's Split.
3. WHEN an expense is created with split strategy "percentage", THE Expense_Service SHALL compute each participant's Split as their percentage of the total, where all percentages must sum to 100, and distribute any Decimal remainder to the first participant.
4. IF a "percentage" split is submitted where the percentages do not sum to 100, THEN THE Expense_Service SHALL return a 422 Unprocessable Entity error.
5. IF an "exact" split is submitted where the amounts do not sum to the expense total within 0.01 currency units, THEN THE Expense_Service SHALL return a 422 Unprocessable Entity error.
6. THE Expense_Service SHALL record the split strategy used on each Expense for auditability.

---

### Requirement 7: Expense Editing and Deletion

**User Story:** As a group member, I want to edit or delete an expense I recorded, so that I can correct mistakes.

#### Acceptance Criteria

1. WHEN the original payer or a group admin submits an update to an existing expense with valid new values, THE Expense_Service SHALL update the expense and its Splits, recalculate affected Balances, invalidate relevant Cache entries, and return the updated expense.
2. WHEN the original payer or a group admin deletes an expense, THE Expense_Service SHALL soft-delete the expense, reverse the Balance changes caused by that expense, invalidate relevant Cache entries, and return a 200 response.
3. THE Expense_Service SHALL prevent a non-admin, non-payer member from editing or deleting an expense, returning a 403 Forbidden error.
4. WHEN an expense is edited or deleted, THE Expense_Service SHALL record an audit entry capturing the actor, timestamp, and the previous values.

---

### Requirement 8: Balance Calculation

**User Story:** As a group member, I want to see who owes whom and how much, so that I know the current state of debts in the group.

#### Acceptance Criteria

1. WHEN an authenticated group member requests the balance summary for a group, THE Balance_Service SHALL return each member's net balance (positive = owed money, negative = owes money) computed from all non-deleted expenses and settlements in that group.
2. WHEN an authenticated user requests their overall balance across all groups, THE Balance_Service SHALL return the aggregated net balance per counterparty, collapsing multi-group debts between the same two users.
3. THE Balance_Service SHALL use Decimal arithmetic for all balance computations and SHALL NOT use floating-point arithmetic.
4. WHEN a balance is requested and a valid cached result exists in the Cache, THE Balance_Service SHALL return the cached result without recomputing.
5. WHEN an expense or settlement is created, updated, or deleted, THE Balance_Service SHALL invalidate the Cache entries for all affected groups and users within the same database transaction.
6. THE Balance_Service SHALL compute balances from the ledger of expenses and settlements and SHALL NOT store a mutable running balance that can drift from the ledger.

---

### Requirement 9: Debt Simplification

**User Story:** As a group member, I want to see a simplified list of who should pay whom, so that the number of transactions needed to settle up is minimized.

#### Acceptance Criteria

1. WHEN an authenticated group member requests simplified debts for a group, THE Balance_Service SHALL apply a greedy debt-simplification algorithm that produces a minimal set of directional Debt records such that all net balances are satisfied.
2. THE Balance_Service SHALL guarantee that the simplified Debt set is equivalent to the original balance state, meaning applying all simplified Debts results in all member balances reaching zero.
3. WHEN the group has no outstanding Debts, THE Balance_Service SHALL return an empty list.
4. THE Balance_Service SHALL cache the simplified Debt result and invalidate it whenever an expense or settlement changes the group's balance.

---

### Requirement 10: Settlement Recording

**User Story:** As a group member, I want to record a payment I made to another member, so that the debt is reduced or cleared.

#### Acceptance Criteria

1. WHEN a group member submits a settlement with a valid payer, payee (both must be group members), a positive Decimal amount, and a date, THE Settlement_Service SHALL persist the settlement, update the Balance between the two users in that group, invalidate relevant Cache entries, and return a 201 response.
2. IF the settlement amount is zero or negative, THEN THE Settlement_Service SHALL return a 422 Unprocessable Entity error.
3. IF the payer and payee are the same user, THEN THE Settlement_Service SHALL return a 422 Unprocessable Entity error.
4. WHEN a group member requests the settlement history for a group, THE Settlement_Service SHALL return settlements in reverse chronological order, paginated at 20 items per page.
5. WHEN a group admin or the original payer deletes a settlement, THE Settlement_Service SHALL soft-delete the record, reverse the Balance change, invalidate relevant Cache entries, and return a 200 response.

---

### Requirement 11: Activity Feed

**User Story:** As a group member, I want to see a chronological feed of recent activity in my groups, so that I stay informed about new expenses and settlements.

#### Acceptance Criteria

1. WHEN an authenticated user requests their activity feed, THE Notification_Service SHALL return the 50 most recent events across all their groups, ordered by timestamp descending, where each event includes the event type, actor name, group name, amount (if applicable), and timestamp.
2. WHEN an expense is created, edited, or deleted in a group, THE Notification_Service SHALL create an activity event for all members of that group.
3. WHEN a settlement is recorded or deleted in a group, THE Notification_Service SHALL create an activity event for the payer and payee.
4. THE Notification_Service SHALL mark events as read when the user views the activity feed and SHALL return an unread event count on each API response that includes user context.

---

### Requirement 12: Search and Filtering

**User Story:** As a group member, I want to search and filter expenses, so that I can quickly find specific transactions.

#### Acceptance Criteria

1. WHEN a group member submits a search request with a keyword, THE Expense_Service SHALL return all expenses in that group whose description contains the keyword (case-insensitive), paginated at 20 items per page.
2. WHEN a group member submits a filter request with a date range, THE Expense_Service SHALL return all expenses in that group within that date range, paginated at 20 items per page.
3. WHEN a group member submits a filter request specifying a payer user id, THE Expense_Service SHALL return all expenses in that group paid by that user, paginated at 20 items per page.
4. WHEN multiple filter parameters are combined, THE Expense_Service SHALL apply all filters conjunctively (AND logic).

---

### Requirement 13: API-First Design and Versioning

**User Story:** As a future mobile developer, I want a versioned, well-documented REST API, so that I can build a mobile client without breaking changes.

#### Acceptance Criteria

1. THE System SHALL expose all data-mutating and data-reading endpoints under the path prefix `/api/v1/`.
2. THE System SHALL serve an OpenAPI 3.0 schema at `/api/v1/openapi.json` and an interactive Swagger UI at `/api/v1/docs`.
3. WHEN a client sends a request with an `Accept: application/json` header to any `/api/v1/` endpoint, THE System SHALL return a JSON response with appropriate HTTP status codes.
4. THE System SHALL include a `X-Request-ID` header in every response, using the value from the incoming request if present, or generating a UUID v4 if absent.
5. THE System SHALL return RFC 7807 Problem Details JSON objects for all error responses, including `type`, `title`, `status`, `detail`, and `instance` fields.

---

### Requirement 14: HTMX Frontend

**User Story:** As a user accessing the app via a browser, I want a responsive web interface, so that I can manage expenses without a separate mobile app.

#### Acceptance Criteria

1. WHEN an unauthenticated browser request is made to any protected page, THE System SHALL redirect the browser to the login page.
2. WHEN a user performs an action via the HTMX frontend (create expense, settle up, etc.), THE System SHALL return an HTML partial that HTMX swaps into the page without a full reload.
3. THE System SHALL serve all Jinja2 templates with TailwindCSS styles and SHALL NOT require a separate build step for CSS in development mode (CDN usage is acceptable for development).
4. WHEN a form submission results in a validation error, THE System SHALL return an HTML partial containing inline error messages adjacent to the relevant form fields.
5. THE System SHALL provide a dashboard page showing the authenticated user's groups, overall balance summary, and recent activity feed.

---

### Requirement 15: Data Integrity and Transaction Safety

**User Story:** As a system operator, I want all financial operations to be atomic, so that partial failures never leave the database in an inconsistent state.

#### Acceptance Criteria

1. WHEN an expense is created, THE System SHALL persist the Expense record, all Split records, and the Cache invalidation within a single database transaction, rolling back all changes if any step fails.
2. WHEN a settlement is created, THE System SHALL persist the Settlement record and the Cache invalidation within a single database transaction, rolling back all changes if any step fails.
3. WHEN an expense or settlement is deleted, THE System SHALL apply the soft-delete and the Balance reversal within a single database transaction.
4. THE System SHALL use database-level constraints (foreign keys, check constraints, unique indexes) to enforce referential integrity and prevent invalid data states.
5. THE System SHALL use optimistic locking or row-level locking on Balance-affecting operations to prevent race conditions when concurrent requests modify the same group's data.

---

### Requirement 16: Caching Strategy

**User Story:** As a system operator, I want frequently-read data to be cached, so that the database is not overloaded under normal usage.

#### Acceptance Criteria

1. WHEN a balance or simplified debt result is computed, THE Balance_Service SHALL store the result in the Cache with a TTL of 300 seconds.
2. WHEN an expense, settlement, or group membership changes, THE Balance_Service SHALL delete the affected Cache keys before the database transaction commits.
3. WHEN the Cache is unavailable, THE Balance_Service SHALL fall back to computing results directly from the database and SHALL NOT return an error to the client due to Cache unavailability alone.
4. THE System SHALL use cache key namespacing in the format `{entity}:{id}:{operation}` to prevent key collisions across different data types.

---

### Requirement 17: Security

**User Story:** As a system operator, I want the application to follow security best practices, so that user data and financial records are protected.

#### Acceptance Criteria

1. THE Auth_Service SHALL sign JWTs using the HS256 algorithm with a secret key of at least 32 characters loaded from an environment variable.
2. THE System SHALL enforce HTTPS in production by setting the `Strict-Transport-Security` header on all responses.
3. THE System SHALL set `HttpOnly` and `Secure` flags on any cookies used for session management.
4. WHEN a client makes more than 100 requests per minute to the API from the same IP address, THE System SHALL return a 429 Too Many Requests response.
5. THE System SHALL sanitize all user-supplied string inputs to prevent stored cross-site scripting (XSS) by escaping HTML entities before persisting or rendering.
6. THE System SHALL validate and reject JWT tokens that have been tampered with, returning a 401 Unauthorized error.

---

### Requirement 18: Database Migrations

**User Story:** As a developer, I want database schema changes to be managed through versioned migrations, so that the schema can be evolved safely across environments.

#### Acceptance Criteria

1. THE System SHALL use Alembic to manage all database schema changes, with migration scripts stored in a `migrations/` directory.
2. WHEN a new migration is applied, THE System SHALL record the migration version in the `alembic_version` table so the current schema version is always known.
3. THE System SHALL provide both `upgrade` and `downgrade` functions in every migration script to allow rollback.
4. WHEN the application starts, THE System SHALL verify that the database schema is at the latest migration version and SHALL log a warning if it is not.

---

### Requirement 19: Containerization and Configuration

**User Story:** As a developer or operator, I want the application to run in Docker containers with environment-based configuration, so that it can be deployed consistently across environments.

#### Acceptance Criteria

1. THE System SHALL provide a `Dockerfile` that builds a production-ready image using a multi-stage build, with the final image based on a slim Python base image.
2. THE System SHALL provide a `docker-compose.yml` that starts the application, PostgreSQL, and Redis services with a single command.
3. THE System SHALL load all configuration (database URL, Redis URL, JWT secret, allowed origins, etc.) from environment variables, with no secrets hardcoded in source files.
4. WHERE a `docker-compose.override.yml` is present, THE System SHALL use it to apply development-specific overrides such as volume mounts and debug settings.
5. THE System SHALL provide a `.env.example` file listing all required environment variables with placeholder values and inline documentation comments.

---

### Requirement 20: Observability and Health

**User Story:** As a system operator, I want health check and structured logging endpoints, so that I can monitor the application in production.

#### Acceptance Criteria

1. THE System SHALL expose a `GET /health` endpoint that returns a 200 response with JSON indicating the status of the application, database connectivity, and Cache connectivity.
2. WHEN the database is unreachable, THE System SHALL return a `GET /health` response with HTTP 503 and a JSON body indicating which dependency is unhealthy.
3. THE System SHALL emit structured JSON logs for every request, including the request method, path, status code, duration in milliseconds, and `X-Request-ID`.
4. THE System SHALL emit structured JSON logs for every unhandled exception, including the exception type, message, stack trace, and `X-Request-ID`.
5. WHEN the Cache is unreachable, THE System SHALL log a warning-level structured event and continue serving requests using the database fallback.
