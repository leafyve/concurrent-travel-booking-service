# ADR 0001 — PostgreSQL as the inventory source of truth

**Status:** Accepted · **Context:** independent portfolio project (not Klook).

## Context
Inventory correctness (no overselling) is the core requirement. Correctness must
survive concurrent requests, retries, and process restarts.

## Decision
Use **PostgreSQL as the single, authoritative store** for inventory. All capacity
checks and mutations happen inside database transactions using row locks
(`SELECT … FOR UPDATE`) and are backed by `CHECK` constraints. No in-memory lock,
cache, or counter is trusted for correctness.

## Consequences
- Correctness is guaranteed by the engine (locks + constraints), not by hoping
  application code is race-free.
- A single very hot slot serializes its writes — acceptable, and per-slot rather
  than global.
- Caches/read-replicas may serve reads but never authorize a write.

## Alternatives considered
- **In-memory lock / Redis counter:** fast but loses correctness on multi-process
  deployments and restarts; a cache miss or eviction can oversell.
- **Optimistic-only (version compare + retry):** viable, but produces
  client-visible retry storms on hot rows; we keep a `version` column for
  optimistic checks where cheap but rely on row locks for the hot path.
