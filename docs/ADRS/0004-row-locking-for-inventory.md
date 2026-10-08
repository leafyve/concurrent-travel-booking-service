# ADR 0004 — Row locking (`SELECT … FOR UPDATE`) for inventory mutation

**Status:** Accepted · **Context:** independent portfolio project (not Klook).

## Context
The check-then-update on a slot's counters is a classic race. We need it to be
atomic per slot without relying on the strongest (and most retry-prone) isolation
level.

## Decision
Take a **pessimistic row lock** on the slot row (`SELECT … FOR UPDATE`) before
reading/mutating its counters, at the default **READ COMMITTED** isolation. For
background scans that must not block each other, use `FOR UPDATE SKIP LOCKED`.

## Consequences
- Concurrent reservations for the *same* slot serialize; different slots run in
  parallel. No serialization-failure retry loop for the hot path.
- Combined with the `reserved + confirmed <= capacity` CHECK, overselling is
  impossible even under a code bug.
- Long-held locks would hurt throughput, so transactions are kept short (lock →
  check → update → insert → commit).

## Alternatives considered
- **SERIALIZABLE isolation:** also correct but surfaces `40001` serialization
  failures that clients/services must retry; more moving parts for the same
  guarantee.
- **Optimistic concurrency only:** kept as a secondary tool (`version` column) but
  not the primary mechanism, to avoid retry storms on hot slots.
