# ADR 0002 — Modular monolith instead of microservices

**Status:** Accepted · **Context:** independent portfolio project (not Klook).

## Context
The system has several concerns (booking, merchant, payments, workers) that could
be separate services. The priority is correctness, clarity, and defensibility in
an interview — not organisational scaling.

## Decision
Build a **modular monolith**: one deployable FastAPI app with clear internal
layers (routes → services → repositories → domain), plus two lightweight worker
processes that share the same codebase and database.

## Consequences
- Business operations use **local ACID transactions** (state change + outbox event
  commit together) — no distributed transactions or sagas needed.
- One codebase to test, lint, type-check, and reason about.
- Horizontal scaling is still available (stateless API replicas; multiple
  workers via `SKIP LOCKED`).
- If a true bounded context needed independent scaling later, the module
  boundaries make extraction straightforward.

## Alternatives considered
- **Microservices (separate booking/payment/inventory services):** adds network
  calls, eventual consistency, and operational overhead that would *reduce*
  correctness clarity here. Explicitly out of scope (as are Kubernetes/Kafka).
