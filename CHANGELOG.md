# CHANGELOG — PlayerOnePay v1 → v2

## Summary

v2 is a ground-up architectural rewrite. The original v1 was a working prototype —
flat module layout, synchronous SQLite, plain-text passwords in request payloads,
no auth, no error handling standard. v2 makes every one of those production concerns
explicit and solves them. Below is a precise account of every change.

---

## 🏗 Architecture

### v1
- Single-file flat layout: `main.py`, `crud.py`, `models.py`, `schemas.py`, `database.py`
- No separation of concerns — route handlers called `db.add()` directly
- All logic in CRUD functions, no service layer
- SQLite only, synchronous `sessionmaker`
- No versioning — routes at `/users`, `/transactions` etc.

### v2
```
app/
  core/        — config, security, logging, exceptions
  db/          — async engine, session factory, declarative base
  models/      — SQLAlchemy 2.x ORM models
  schemas/     — Pydantic v2 request/response schemas
  services/    — business logic layer (UserService, TransactionService)
  api/v1/      — versioned routers + FastAPI dependencies
  middleware/  — cross-cutting concerns (request ID, logging)
```
- **Service layer** isolates all business logic from HTTP concerns
- **Versioned API** under `/api/v1` — adding `/api/v2` never breaks existing clients
- **Async throughout** — `async def` on every route, service method, and DB call
- **PostgreSQL-ready** with SQLite fallback for local development

---

## 🔒 Security

### v1 — Critical issues fixed in v2

| Issue | v1 | v2 |
|-------|----|----|
| Passwords | Stored in plain text in `Customer.password` field | bcrypt-hashed via `passlib`, 12 rounds, never stored raw |
| Authentication | **None** — any caller could access any endpoint | JWT bearer tokens (access + refresh), HMAC-signed |
| Authorisation | **None** — no role or ownership checks | Role-based (`UserRole` enum) + resource ownership enforcement |
| API keys | Not implemented | SHA-256-hashed, shown once on generation, `prefix_` namespaced |
| Webhook validation | Not implemented | HMAC-SHA256 signature on every inbound webhook |
| Token type | Not implemented | `"type": "access"` / `"type": "refresh"` claim prevents token misuse |
| Account status | Not checked | `SUSPENDED` / `CLOSED` accounts rejected at auth layer |
| Error leakage | Raw exceptions propagated to HTTP responses | All exceptions caught; no tracebacks, stack traces, or SQL exposed |

---

## 🗃 Database

### v1
- `SQLModel` mixing ORM and Pydantic (creates coupling, known issues)
- Synchronous `sessionmaker` — blocks the event loop
- `orm_mode = True` (Pydantic v1 style, deprecated)
- Manual `db.commit()` / `db.refresh()` in every CRUD function — no consistency guarantee
- SQLite only, `test.db` committed to the repo
- No migration system — `SQLModel.metadata.create_all()` on every startup
- `float` for money — floating point errors in financial data

### v2
- Pure SQLAlchemy 2.x ORM — no SQLModel coupling
- **Async engine** (`asyncpg` for Postgres, `aiosqlite` for SQLite)
- Session managed as a dependency — auto-commit on success, auto-rollback on error
- **Alembic** for versioned schema migrations with async support
- **`Numeric(18, 4)`** (Decimal) for all monetary values — no floating point errors
- **ULID primary keys** — sortable, URL-safe, no sequential ID guessing
- `pgdata` volume — dev database never committed to source control

---

## 📦 Models

### v1 → v2 model changes

**User**
- `phone_number` was the primary key — changed to ULID `id`; phone has a unique index
- Added `email`, `status`, `role`, `api_key_hash`, `balance`, `currency` fields
- Removed `user_id: str` (duplicate of PK)
- `balance` now a proper field on `User` (v1 tried to access `user.balance` in crud.py but it wasn't defined on the model — would have raised `AttributeError` at runtime)

**Transaction**
- `id` and `transaction_id` were separate fields with unclear purpose — merged into ULID `id`, with `reference` (human-readable) and `external_reference` (processor's ID) as distinct fields
- `amount: float` → `amount: Numeric(18,4)` — precision fix
- `balance` field removed from Transaction — replaced by `balance_before` / `balance_after` (immutable snapshot at time of transaction)
- `transaction_date: str` → `created_at: DateTime(timezone=True)` — proper timestamping
- Added **`TransactionEvent`** table — immutable audit trail of every status change
- Added `idempotency_key` unique index
- Added `channel` (USSD, NIP, QR, etc.)
- Added `fee` field — fee calculation was absent in v1

**KYC**
- Added `tier` (0–3), `daily_limit`, `monthly_limit` — v1 KYC was a stub with only `verification_status: str`
- Added document reference fields (`id_front_ref`, etc.) — store S3 keys, not raw data
- Added `rejection_reason` and `reviewer_id` for admin workflow

**New: TransactionEvent**
- Append-only audit log of every status transition
- Records `from_status`, `to_status`, `actor`, `note`, `created_at`

**Removed: Customer / Business / Merchant / Individual (separate tables)**
- v1 had 4 overlapping entity types with duplicate fields and circular FK confusion
- v2 uses a single `User` table with `role: UserRole` enum — cleaner, less join complexity
- Agent and ATM kept as separate tables (they have genuinely distinct fields)

---

## 🔄 Transaction State Machine

### v1
- `transaction_status` could be set to any value at any time — no validation
- `update_transaction` in crud.py directly overwrites status

### v2
```python
VALID_TRANSITIONS = {
    INITIATED: {PENDING, CANCELLED},
    PENDING:   {PROCESSING, FAILED, CANCELLED},
    PROCESSING:{SUCCESS, FAILED},
    SUCCESS:   {REVERSED, REFUNDED},
    ...
}
```
- Invalid transitions return `422 invalid_state_transition`
- Balance is only debited/credited on `SUCCESS` — not on initiation
- Every transition is recorded in `TransactionEvent`

---

## 💸 Fee Engine

### v1
- No fee calculation anywhere in the codebase

### v2
- `_calculate_fee(transaction_type, amount)` in `TransactionService`
- Per-type rate schedule (e.g. `send_money=1.5%`, `deposit=0%`)
- Hard cap at ₦500 max fee
- `fee` stored on the transaction record
- `balance_after = balance_before - amount - fee` on debit transactions

---

## 🪪 Idempotency

### v1
- Not implemented — retrying a failed request would create duplicate transactions

### v2
- `Idempotency-Key` header on all mutating endpoints
- Unique constraint on `transactions.idempotency_key`
- `TransactionService.create_transaction()` checks for existing key before inserting
- Returns the original transaction response on duplicate — safe to retry

---

## 📡 Request Tracing

### v1
- No request IDs
- No structured logging
- No response timing

### v2
- `RequestIDMiddleware` generates a ULID `X-Request-ID` per request (or echoes caller's)
- `structlog` structured JSON logging in production, coloured console in dev
- Every log line carries `request_id`, `method`, `path`, `status_code`, `duration_ms`
- Context vars bound per request — all log lines within a request share the same `request_id`
- `X-Response-Time-ms` header on every response

---

## 📬 Webhooks

### v1
- No webhook support

### v2
- `POST /api/v1/webhooks/payment-processor`
- HMAC-SHA256 signature validation on every inbound request
- Event router dispatches to typed handlers: `transaction.success`, `transaction.failed`, `transaction.reversed`
- Handlers call `TransactionService.update_status()` — same state machine, same audit trail
- Invalid signature → `401 Unauthorized` immediately, no payload processed

---

## 📐 Response Envelope

### v1
- Inconsistent — some endpoints returned the model directly, others returned `{"message": "..."}`, others raised unhandled exceptions that FastAPI wrapped in its own format

### v2
Every response is one of two shapes:

**Success** — `APIResponse[T]`
```json
{ "success": true, "data": {...}, "message": "OK", "request_id": "..." }
```

**Error** — `ErrorResponse`
```json
{ "success": false, "error_code": "insufficient_funds", "message": "...", "detail": null, "request_id": "..." }
```

**Paginated** — `PaginatedResponse[T]`
```json
{ "success": true, "data": [...], "total": 100, "page": 1, "per_page": 20, "has_next": true }
```

---

## 🧪 Testing

### v1
- No tests
- `test.db` committed to source (16KB SQLite file)

### v2
- `pytest-asyncio` test suite with async fixtures
- **In-memory SQLite** per test function — fully isolated, no shared state
- `conftest.py` provides: `db`, `client`, `registered_user`, `auth_headers` fixtures
- `test_users.py` — registration, login, profile, token refresh
- `test_transactions.py` — deposits, insufficient funds, idempotency, state machine, pagination
- `test_health_and_security.py` — health probes, auth enforcement, webhook HMAC, payment link ownership
- Coverage enforced at 70% minimum in CI

---

## 🚀 Ops / Deployment

### v1
- No Docker
- No CI/CD
- No health checks
- No migration system
- `echo=True` always on (logs every SQL statement in production)

### v2
- **Dockerfile** — non-root user, multi-worker uvicorn, healthcheck
- **docker-compose.yml** — API + Postgres + Redis + migrate service
- **GitHub Actions CI** — lint (ruff) → type check (mypy) → tests → security scan (bandit + safety) → Docker build
- `/health` liveness probe
- `/ready` readiness probe (checks DB connectivity)
- Alembic versioned migrations — `alembic upgrade head` in deploy pipeline
- `echo=True` only when `DEBUG=true`
- Sentry integration (production only, gated by `SENTRY_DSN`)
- `pool_pre_ping=True` — stale connections recycled automatically

---

## 🗑 Removed

| Item | Reason |
|------|--------|
| `modelss.py` | Empty file, no content |
| `test.db` | Binary SQLite file committed to source; tests now use in-memory DB |
| `Customer` / `Business` / `Merchant` / `Individual` tables | Collapsed into `User.role` |
| Duplicate `create_user` function | Defined twice in crud.py |
| `class User(BaseModel)` in `main.py` | Duplicate of schema already in `schemas.py` |
| `orm_mode = True` | Replaced with Pydantic v2 `model_config = {"from_attributes": True}` |
| `SQLModel` dependency | Replaced with pure SQLAlchemy 2.x + Pydantic v2 |
