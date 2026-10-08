# Implementation Status

Running checklist for the **Travel Experience Inventory & Booking Orchestration
Service**. Everything marked ✅ was verified by running a command, not by merely
creating files.

> Independent educational portfolio project. Not affiliated with Klook.

## Environment notes (this build machine)

- Python **3.12.10** in a local `.venv`.
- **PostgreSQL 16.4** running locally (portable binaries, port 55432) — used for
  real integration & concurrency tests.
- **Docker is NOT installed on this build machine.** Docker/Compose/CI assets are
  authored and their YAML is validated, but `docker build` / `compose up` were
  **not** executed here. Reported honestly in the README and DEPLOYMENT docs.

## Phase checklist

| Phase | Item | Status | Verified by |
|-------|------|--------|-------------|
| 1 | Repo skeleton, config, venv, deps | ✅ | install + import |
| 2 | ORM models (11 tables) + constraints | ✅ | metadata + migration review |
| 2 | Alembic initial migration | ✅ | `upgrade head` on empty DB; up+down test |
| 2 | Auth (bcrypt + JWT + roles + ownership) | ✅ | 8 auth API tests |
| 2 | Seed data (fictional) | ✅ | 5 users / 5 exp / 45 slots / 2 bookings |
| 3 | Experience search + availability | ✅ | API tests (no N+1 via EXISTS) |
| 3 | Reservations + idempotency | ✅ | API + concurrency tests |
| 3 | Booking confirm | ✅ | API + concurrency tests |
| 3 | Cancellation + policy + restore-once | ✅ | API + concurrency tests |
| 4 | Payment webhook (HMAC + replay + dedup) | ✅ | 9 webhook API tests |
| 4 | Merchant inventory sync | ✅ | 6 merchant API tests |
| 4 | Reservation-expiry worker | ✅ | integration + concurrency + run-once |
| 4 | Transactional outbox worker | ✅ | integration + concurrency + run-once |
| 5 | RFC7807 errors | ✅ | failure-path tests |
| 5 | Structured JSON logging + request id | ✅ | observed in server/demo output |
| 5 | Health `/live` `/ready` | ✅ | smoke tests |
| 5 | Prometheus `/metrics` | ✅ | endpoint + demo |
| 6 | Unit / API / integration / concurrency tests | ✅ | **99 passed** |
| 6 | Coverage | ✅ | **92% overall / 93% core / 100% domain** |
| 6 | Ruff format + lint | ✅ | clean |
| 6 | mypy | ✅ | Success, 79 files |
| 7 | Locust load test + benchmark | ✅ | run; bottleneck found & fixed |
| 7 | Dockerfile / Compose / Makefile / CI / Caddyfile | ✅ authored | YAML validated (**not built** — no Docker here) |
| 8 | README + ARCHITECTURE + DATA_MODEL + sequences | ✅ | written with Mermaid |
| 8 | CONCURRENCY + API_CONTRACT + 7 ADRs | ✅ | written |
| 8 | INCIDENT + LOAD_TEST_REPORT + JOB_ALIGNMENT | ✅ | written (real numbers) |
| 8 | INTERVIEW_WALKTHROUGH + RECRUITER_DEMO + DEPLOYMENT | ✅ | written |

## Verified commands (final run)

- `ruff format --check .` → 121 files already formatted.
- `ruff check .` → All checks passed.
- `mypy app` → Success: no issues found in 79 source files.
- `alembic upgrade head` on an empty database → all 11 tables + `alembic_version`.
- `python -m scripts.seed` → seeded fictional data (idempotent on re-run).
- `python -m scripts.demo` → all lifecycle invariants held.
- `pytest -q` → **99 passed**; `--cov=app` → **92%** (core domain+services 93%).
- `locust … --users 50 --run-time 30s` → ~158 req/s; bcrypt bottleneck fixed.

## Known gaps (see README §19)

- Docker image not built/run here (no Docker on build machine).
- No external deployment performed.
- Outbox delivery and payments are simulated; refunds are computed, not executed.
