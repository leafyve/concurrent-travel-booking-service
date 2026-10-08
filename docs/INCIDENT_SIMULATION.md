# Incident Simulation — Overselling the final remaining units

> **This is a simulated, educational incident write-up** used to demonstrate a
> debugging/postmortem process. It is **not** a real production incident and has
> no connection to Klook or any company.

## Summary

A hypothetical earlier version of the reservation endpoint checked slot
availability and then updated the counters **without** locking the slot row. Under
concurrent requests for a slot's final seats, two requests could both observe
"seats available" and both succeed — **overselling the last units**.

## Symptoms

- Occasional bookings exceeding a slot's `capacity`.
- `reserved_quantity + confirmed_quantity > capacity` observed in support tooling.
- Intermittent and load-dependent; impossible to reproduce with single requests.

## Reproduction

Deterministic reproduction with a real database and genuine concurrency:

```bash
pytest tests/concurrency/test_no_oversell.py -q
```

Scenario: one slot, `capacity = 5`, **20 concurrent** single-unit reservation
requests via `asyncio.gather`. A vulnerable "read-then-write" implementation lets
more than 5 succeed.

## Root cause

A **check-then-act race**. Between reading availability and writing the new
counter, another transaction did the same, so both passed the check:

```
T1: read reserved=4 (cap 5) -> ok        T2: read reserved=4 (cap 5) -> ok
T1: write reserved=5                       T2: write reserved=5  (should be 6!)
```

Nothing forced the two transactions to serialize on the slot.

## Alternatives considered

1. **`SERIALIZABLE` isolation** — correct, but clients/services must catch and
   retry `40001` serialization failures.
2. **Application-level mutex / Redis lock** — loses correctness across processes
   and on lock loss; adds an external dependency in the critical path.
3. **Pessimistic row lock (`SELECT … FOR UPDATE`) + DB CHECK constraint** —
   serializes writers per slot at READ COMMITTED, with the database as a hard
   backstop.

## Selected fix

Option 3. The reservation service now:

1. Locks the slot row: `SELECT … FOR UPDATE` (`experience_repo.get_slot_for_update`).
2. Checks and mutates counters inside that lock, in one transaction.
3. Is backed by `CHECK (reserved_quantity + confirmed_quantity <= capacity)` so an
   oversold row can never be committed even if the app logic regresses.

## Regression test

`tests/concurrency/test_no_oversell.py` asserts that with capacity 5 and 20
concurrent requests, **exactly 5 succeed (201)**, 15 receive `409`, and the DB
counters are consistent. It runs against real PostgreSQL and fails on any
regression. Complementary tests cover double-booking, double-cancellation,
parallel expiry, and idempotency races.

## Remaining risks

- A single extremely hot slot serializes all its writes (throughput ceiling by
  design; would need sharded counters/queueing to exceed).
- The guarantee assumes the CHECK constraint and locking code stay in place — both
  are covered by tests that would fail if removed.
