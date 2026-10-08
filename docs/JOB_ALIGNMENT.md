# Job Alignment

How this project's **verified** evidence maps to common expectations for a
backend software-engineering internship. Independent educational project; not
affiliated with Klook, and **not** claimed to be equivalent to any company's
production scale.

| Competency | Evidence in this project | How it was verified |
|------------|--------------------------|---------------------|
| **Technical solution design / ownership** | Layered modular monolith; 7 recorded ADRs; explicit transaction and concurrency design | `docs/ARCHITECTURE.md`, `docs/ADRS/`, `docs/CONCURRENCY_AND_IDEMPOTENCY.md` |
| **Python backend development** | FastAPI + SQLAlchemy 2 async + Pydantic v2; clean routes→services→repos→domain layering | Code compiles, imports, runs; `mypy` clean on 79 files |
| **REST API design** | Versioned resources, correct status codes, RFC 7807 errors, pagination, idempotency headers | `docs/API_CONTRACT.md`; 46 API tests pass |
| **Relational data modelling** | 11 tables, FKs, unique/check constraints, composite indexes, migrations | `docs/DATA_MODEL.md`; Alembic up/down verified |
| **Transaction safety** | State change + inventory mutation + outbox event commit atomically | Integration tests; constraint tests |
| **Concurrent inventory management** | `FOR UPDATE` row locks + CHECK constraints; no overselling under load | `test_no_oversell`: cap 5, 20 concurrent → exactly 5 |
| **Idempotent operations** | Idempotency keys + fingerprints; webhook event dedup | `test_idempotent_concurrent`, `test_duplicate_event_deduplicated` |
| **Validation & error handling** | Pydantic validation; typed error hierarchy; safe problem responses | Failure-path tests across API suites |
| **Merchant/partner integration** | Signed partner inventory-sync API with ownership + capacity-floor rules | `test_merchant.py` |
| **Background processing** | Two DB-backed workers with `SKIP LOCKED`, retries, metrics | `test_expiry*`, `test_outbox*`, worker run-once tests |
| **Automated testing** | 99 tests: unit (incl. Hypothesis), API, integration, concurrency | `pytest -q` → 99 passed |
| **High-quality / maintainable code** | Ruff + mypy strict-ish; small services; no broad `except: pass` | `ruff check` clean; `mypy` clean |
| **Performance measurement** | Real Locust benchmark; found & fixed an event-loop-blocking bottleneck | `docs/LOAD_TEST_REPORT.md` (before/after measured) |
| **Observability** | JSON logs w/ correlation id; `/health/*`; Prometheus `/metrics` | Verified via requests + demo output |
| **Docker deployment** | Non-root multi-stage Dockerfile; Compose (API+DB+2 workers+migrate) | Authored; YAML validated (**not built** — no Docker on build machine) |
| **CI/CD** | GitHub Actions: format, lint, types, Postgres, migrate, tests, image build | `ci.yml` authored & YAML-validated |
| **End-to-end delivery** | Search → reserve → confirm → pay → cancel demonstrated end-to-end | `scripts/demo.py` runs green against a live server |
| **Communication / documentation** | README + architecture, data-model, sequence, concurrency, ADR, incident, deployment docs | This `docs/` tree |
| **Independent priority management** | Phased plan with a running status doc; honest reporting of what is/ isn't done | `docs/IMPLEMENTATION_STATUS.md` |

**Honest scoping:** this is a focused, deeply-tested backend, not a distributed
system at millions-of-users scale. See §"What would change at scale" in
`docs/INTERVIEW_WALKTHROUGH.md`.
