# ADR 0005 — Separate reservation-expiry worker

**Status:** Accepted · **Context:** independent portfolio project (not Klook).

## Context
Reservations hold inventory for a TTL (default 10 min). Expired holds must return
their seats. This must be reliable across restarts and safe to run in parallel.

## Decision
Run expiry in a **separate worker process** (`python -m app.workers.cli expiry`)
that scans expired, still-active reservations in **bounded batches** using
`FOR UPDATE SKIP LOCKED`, releases inventory, marks them expired, and emits outbox
events — all in one transaction per batch. Explicitly **not** an in-process
FastAPI timer as the production design.

## Consequences
- Survives API restarts/deploys; scales horizontally (multiple workers claim
  disjoint batches).
- Idempotent and re-runnable: releasing inventory is tied to the status
  transition under a row lock, so a seat is never released twice (verified by
  `test_expiry_safe`).
- A confirm racing an expiry is deterministic: the confirm blocks on the row lock,
  then observes `expired` and returns `409`.

## Alternatives considered
- **In-process `asyncio` timer:** simple but dies with the process, doesn't scale,
  and duplicates work across API replicas. Kept only as a convenience for local
  demos, never as the source of truth.
- **`pg_cron`:** viable but couples business logic to a DB extension and is harder
  to test.
