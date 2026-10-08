# Concurrent Travel Booking & Inventory Service

A backend service for reserving and booking limited-capacity travel experiences.
It uses PostgreSQL row locks and constraints to protect inventory, idempotency
keys for retried operations, signed payment webhooks, reservation expiry, and a
transactional outbox. Payments and event delivery are simulated locally.

> **Independent educational portfolio project.** It is **not** built for,
> commissioned by, connected to, or endorsed by Klook or any company. It uses no
> proprietary assets, private APIs, or copyrighted content. All data is fictional.

---

## 1. What this is

A modular monolith in **Python 3.11+ / FastAPI / PostgreSQL** that models the hard
part of a marketplace like a travel-experiences platform: **selling a fixed,
perishable inventory correctly under concurrency**. One slot with 5 seats must
never become 6 bookings, a retried request must never double-charge or
double-book, and a reservation that expires must return its seats exactly once.

## 2. The problem it solves

Inventory for a dated activity slot is finite and perishable. Customers browse,
hold seats while they pay, then confirm. Under load, many customers race for the
last seats; networks retry; payment providers redeliver webhooks; merchants edit
capacity concurrently. A naive "read count, then write count" design oversells.
This service makes the **database the single source of truth** for inventory and
enforces correctness with row locks, atomic updates, and check constraints.

## 3. Why inventory reservation is difficult

- **Overselling under concurrency.** Two requests both read "1 seat left" and
  both succeed → oversold. Prevented here with `SELECT … FOR UPDATE` row locks
  plus a DB `CHECK (reserved + confirmed <= capacity)`.
- **Duplicate work from retries.** Clients retry on timeouts; the same request
  must not create two reservations/bookings → **idempotency keys** with request
  fingerprinting.
- **Webhook replay.** Providers deliver a payment event more than once → HMAC
  signatures, a replay window, and DB-unique event ids make processing safe.
- **Expiry races.** A reservation can expire at the exact moment a customer
  confirms → row locking makes the outcome deterministic.
- **Exactly-once inventory release.** Cancellations and expiries must return
  seats exactly once, never twice, never negative.

## 4. Architecture overview

A modular monolith plus two worker processes sharing one codebase and database:

```
Customer / Merchant / Payment-provider (simulated)
                    │  HTTPS (JSON, JWT)
                    ▼
        ┌───────────────────────────┐        ┌──────────────────────┐
        │  FastAPI app (API layer)  │        │  reservation-expiry   │
        │  routes → services → repos│        │  worker (batches)     │
        └─────────────┬─────────────┘        ├──────────────────────┤
                      │ SQLAlchemy async     │  transactional-outbox │
                      ▼ (psycopg3)           │  worker (batches)     │
              ┌───────────────┐              └───────────┬──────────┘
              │  PostgreSQL   │◀─────────────────────────┘
              │ (source of    │   FOR UPDATE [SKIP LOCKED], CHECK constraints
              │  truth)       │
              └───────────────┘
```

Layering: **routes** (thin) → **services** (business rules, transaction
boundaries) → **repositories** (queries/locks) → **models** (ORM). Domain logic
(money, policies, signatures, fingerprints) is pure and framework-free. Full
detail with Mermaid diagrams in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 5. Main workflows

| # | Endpoint | What it does |
|---|----------|--------------|
| 1 | `GET /api/v1/experiences` | Search (destination, category, date range, min availability, pagination); no N+1 |
| 2 | `GET /api/v1/experiences/{id}/slots` | Live availability (hides internal reservation counters) |
| 3 | `POST /api/v1/reservations` | Concurrency-safe, idempotent inventory hold (default 10-min TTL) |
| 4 | `POST /api/v1/bookings` | Confirm a reservation → booking (reserved → confirmed, one booking per reservation) |
| 5 | `POST /api/v1/webhooks/payments` | Signed payment webhook: HMAC + replay window + event dedup + amount match |
| 6 | `POST /api/v1/bookings/{id}/cancel` | Idempotent cancel; applies policy; restores inventory exactly once |
| 7 | reservation-expiry worker | Releases seats from expired holds in locked batches |
| 8 | `POST /api/v1/merchant/inventory-updates` | Partner capacity sync; can't drop below committed inventory |
| 9 | transactional-outbox worker | Delivers domain events (at-least-once) to consumers |

Sequence diagrams: [docs/BOOKING_SEQUENCE.md](docs/BOOKING_SEQUENCE.md).

## 6. Technology stack

Python 3.11+ · FastAPI · Pydantic v2 · SQLAlchemy 2.x (async) · psycopg3 ·
PostgreSQL 16 · Alembic · pytest / pytest-asyncio / pytest-cov · Hypothesis ·
HTTPX · Ruff · mypy · Prometheus client · structlog · Docker / Docker Compose ·
GitHub Actions · Locust.

SQLAlchemy is constrained to the 2.0 release series used by the test and typing
audit. A fresh install of 2.1.4 exposed incompatible query-result typing in CI;
the constraint preserves the validated API without changing service code.

## 7. Database model

11 tables: `users`, `merchants`, `experiences`, `experience_slots`,
`reservations`, `bookings`, `payment_attempts`, `idempotency_records`,
`partner_inventory_updates`, `outbox_events`, `audit_events`. UUID keys,
`TIMESTAMPTZ` everywhere, `Numeric` money. Full ERD and constraints in
[docs/DATA_MODEL.md](docs/DATA_MODEL.md).

## 8. Transaction & concurrency strategy

Inventory correctness rests on three layers, described in full in
[docs/CONCURRENCY_AND_IDEMPOTENCY.md](docs/CONCURRENCY_AND_IDEMPOTENCY.md):

1. **Row locks** — the slot row is taken with `SELECT … FOR UPDATE` before its
   capacity is checked and mutated, so concurrent reservations serialize.
2. **Check constraints** — `reserved >= 0`, `confirmed >= 0`,
   `reserved_quantity + confirmed_quantity <= capacity` reject an invalid
   inventory-counter state, independent of application code. Service transactions
   keep those counters consistent with reservation and booking records.
3. **Single transaction** — the reservation/booking, its inventory mutation, and
   its outbox event all commit atomically.

Workers use `FOR UPDATE SKIP LOCKED` so multiple instances process disjoint
batches without blocking or double-processing.

## 9. Idempotency strategy

`POST /reservations` and `POST /bookings` require an `Idempotency-Key` header.
The operation and an idempotency record (unique on key+endpoint+actor) commit in
one transaction. A retry with the **same** payload replays the stored response; a
retry with a **different** payload returns **409**; concurrent duplicates resolve
via the unique constraint (loser rolls back and replays the winner).

## 10. Webhook security

`"{timestamp}.{raw_body}"` is signed with HMAC-SHA256 (constant-time compare).
Requests outside a configurable replay window are rejected; provider event ids
are unique in the database so a replay is a safe no-op; amount and currency must
match the booking total (integer minor units). The signing secret is never
logged.

## 11. Worker design

Two standalone processes (`python -m app.workers.cli expiry|outbox`) share the
codebase and DB. Each drains bounded batches under `FOR UPDATE SKIP LOCKED`,
commits per batch, records metrics, and sleeps when idle. The outbox is
**at-least-once**; consumers must be idempotent (event payloads carry stable
ids). A DB-backed design — not an in-process timer — so it scales and survives
restarts.

## 12. Testing strategy

Real **PostgreSQL** for integration and concurrency tests (never SQLite), so
constraints and locks behave as in production. Unit tests (incl. Hypothesis
property tests for money/idempotency invariants), API tests over an ASGI
transport, integration tests (constraints, Alembic up/down, outbox, expiry), and
concurrency tests that fire genuinely concurrent requests via `asyncio.gather`.

## 13. Observability

- **Structured JSON logs** (structlog) with a per-request correlation id, method,
  route, status, duration, and actor id. Secrets are never logged.
- **Health**: `GET /health/live`, `GET /health/ready` (readiness checks the DB).
- **Metrics**: `GET /metrics` (Prometheus) — request count/latency, reservations
  created/expired, bookings confirmed/cancelled, inventory conflicts, webhook
  rejections, outbox retries, worker batch duration.

## 14. Local setup

Prerequisites: Python 3.11+ and PostgreSQL 16 (or Docker).

**With Docker (recommended):**

```bash
cp .env.example .env                 # adjust secrets
docker compose up --build -d --wait  # API + Postgres + 2 workers, runs migrations
docker compose run --rm seed         # load fictional demo data
curl localhost:8000/health/ready
```

**Without Docker (local venv + local PostgreSQL):**

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev,load]"
# point DATABASE_URL at your PostgreSQL (see .env.example), then:
alembic upgrade head
python -m scripts.seed
python -m scripts.run_api            # cross-platform runner (see note below)
```

> **Windows note:** psycopg's async mode needs a `SelectorEventLoop`.
> `python -m scripts.run_api`, the workers, and the test suite install the right
> policy automatically. On Linux the default loop already works, so the Docker
> image runs `uvicorn app.main:app` directly.

Common commands (`make help` for all): `make test`, `make lint`,
`make typecheck`, `make cov`, `make demo`, `make load-test`.

The test harness creates and drops a uniquely named test database on a local
PostgreSQL server; it does not reuse the application database's tables. Its
default port is 55432. To test against the Docker service on port 5432:

```powershell
$env:TEST_ADMIN_DATABASE_URL = "postgresql+psycopg://booking:booking@127.0.0.1:5432/booking"
.\.venv\Scripts\python.exe -m pytest -q --cov=app --cov-branch
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy app
```

The API and database ports bind to localhost. Worker containers do not expose
HTTP, so their inherited image HTTP health check is disabled. Only the API and
database have health checks; worker liveness is not a readiness guarantee.
Example credentials, seeded passwords, and test signing keys are public
development fixtures. Supply private signing secrets for any real deployment.
Set `WEBHOOK_SIGNING_SECRET` for `scripts.demo` to match the API configuration.

## 15. API examples

```bash
# Log in (seeded demo account) → JWT
curl -s localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"customer.alice@demo.test","password":"Password123!"}'

# Create an idempotent reservation
curl -s localhost:8000/api/v1/reservations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H 'Content-Type: application/json' \
  -d '{"slot_id":"<slot-uuid>","quantity":2}'
```

Interactive docs at `/docs` (Swagger). Full contract in
[docs/API_CONTRACT.md](docs/API_CONTRACT.md). A scripted end-to-end lifecycle
lives in [scripts/demo.py](scripts/demo.py) (`make demo`).

## 16. Verified test & coverage results

Rechecked on 8 October 2026 using Python 3.12.10 and an isolated test database on
Docker PostgreSQL 16. Integration and concurrency tests use real PostgreSQL.

| Gate | Command | Result |
|------|---------|--------|
| Unit + API + integration + concurrency tests | `pytest -q` | **99 passed** |
| Coverage (combined statement/branch, branch measurement enabled) | `pytest --cov=app --cov-branch` | **92.32%** |
| Branch-only coverage | coverage JSON: 123 / 168 branches | **73.21%** |
| Lint | `ruff check .` | **All checks passed** |
| Format | `ruff format --check .` | **140 files already formatted** |
| Types | `mypy app` | **Success: no issues in 79 source files** |
| Migrations | `alembic upgrade head` on empty DB; `upgrade`+`downgrade` | **pass** |
| Docker build/start | `docker compose up --build -d --wait` | API and database healthy; both workers running |
| Seed | `docker compose --profile tools run --rm seed` | Fictional demo data loaded |
| API lifecycle demo | local dev venv: `python -X utf8 -m scripts.demo` | Reservation, retry, webhook replay, cancellation and inventory invariants passed |

Test breakdown: 32 unit · 46 API · 15 integration · 6 concurrency = **99**.

**Flagship concurrency proof** (`tests/concurrency/test_no_oversell.py`): capacity
5, **20 concurrent** single-unit reservations → **exactly 5 succeed (201)**, 15
receive a deterministic **409**, DB counters consistent.

Coverage excludes `app/main.py`, `app/workers/cli.py`, and migrations. The
rounded 92% result is not a branch-only percentage. Historical layer-specific
coverage and load-test measurements are separate from this publication audit.

## 17. Benchmark results

Recorded during the July 2026 build; not rerun for publication. Run with Locust
(50 users, 25/s spawn, 30s) against the app on the build machine.
These are **environment-specific local figures, not Klook-scale claims.**

- **Environment:** Intel Core i9-13900H (14C/20T), 32 GB RAM, Windows 11,
  Python 3.12.10, PostgreSQL 16.4 (local), single Uvicorn worker.
- **Result (after fix below):** ~**158 req/s** aggregate, latency **p50 8 ms /
  p95 86 ms / p99 340 ms**; read path `GET /experiences` **p50 7 ms / p95 44 ms**.

**A real bottleneck was found and fixed during benchmarking:** synchronous
`bcrypt` password verification was blocking the single-threaded event loop, so
under a burst of concurrent logins the login p50 was ~5.7 s and read tail-latency
spiked to seconds. Moving `bcrypt` to a worker thread (`asyncio.to_thread`)
dropped login p50 to ~0.69 s and read p50 from ~2.7 s to ~0.06 s. Details:
[docs/LOAD_TEST_REPORT.md](docs/LOAD_TEST_REPORT.md).

## 18. Deployment status

No hosted deployment has been performed. The non-root Docker image was built
and the local Compose stack started during the 8 October 2026 publication audit.
The migration job completed, the API readiness endpoint returned HTTP 200, and
both worker processes started. A Caddy example and
[deployment runbook](docs/DEPLOYMENT.md) are included; publishing the repository
does not demonstrate production readiness.

## 19. Known limitations

- Single Uvicorn worker in the local benchmark; no horizontal scaling measured.
- Outbox delivery is simulated (logged), not wired to a real bus; delivery is
  at-least-once by design.
- Payments are simulated; no real provider integration.
- No refund execution (the cancellation computes refund eligibility/amount but
  does not move money).
- Idempotency records are retained (24h TTL field) but not garbage-collected.
- Auth is intentionally minimal (login + JWT + roles); no registration/refresh.

## 20. Future improvements

- Read replicas + caching for search; cursor pagination.
- Real message bus for the outbox (e.g. Kafka/SNS) with a dead-letter queue.
- Rate limiting and per-actor quotas at the edge.
- Idempotency-record cleanup job; partial-index tuning.
- Multi-worker Uvicorn / Gunicorn and a repeatable, documented load rig.
- OpenTelemetry traces alongside the metrics.

## 21. Disclaimer

This is an independent educational portfolio project created to demonstrate
backend engineering skills. It is **not affiliated with, endorsed by, or
connected to Klook** or any other company, uses only fictional data, and contains
no proprietary or copyrighted third-party material.
