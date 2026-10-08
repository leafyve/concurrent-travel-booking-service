# Interview Walkthrough (~7 minutes)

Independent educational portfolio project. Not affiliated with Klook.
A script for explaining the project, plus likely questions with concise answers.

## The 7-minute narrative

**1. Business problem (30s).** Selling limited, dated travel-experience inventory
correctly. A slot with 5 seats must never become 6 bookings, retries must not
double-book, and expired holds must return seats exactly once — all under
concurrent traffic.

**2. Architecture (45s).** Modular monolith: FastAPI, layered routes → services →
repositories → pure domain, on PostgreSQL, plus two worker processes (expiry,
outbox) sharing the codebase and DB. One deployable, local ACID transactions.

**3. Database model (30s).** 11 tables, UUID keys, `TIMESTAMPTZ`, `NUMERIC` money.
The critical table is `experience_slots` with `capacity`, `reserved_quantity`,
`confirmed_quantity` and CHECK constraints.

**4. The reservation transaction (60s).** Lock the slot row (`SELECT … FOR
UPDATE`), check `available = capacity - reserved - confirmed`, increment reserved,
insert the reservation and an outbox event, and write the idempotency record — all
in one transaction. Concurrent reservations for the same slot serialize on the
lock.

**5. Overselling prevention (45s).** Two layers: the row lock removes the
check-then-act race, and a DB `CHECK (reserved + confirmed <= capacity)` makes an
oversold row impossible to persist even with a code bug. Proven: capacity 5, 20
concurrent requests → exactly 5 succeed.

**6. Idempotency (45s).** Reservation/booking require an `Idempotency-Key`. The
operation and a unique idempotency record commit together; same key + same payload
replays; same key + different payload → 409; concurrent duplicates resolve via the
unique constraint (loser rolls back, replays the winner).

**7. Webhook processing (45s).** HMAC-SHA256 over `timestamp.body`, a replay
window, DB-unique event ids for dedup, and amount/currency matched in integer
minor units. The signing secret is never logged.

**8. Background workers (30s).** Expiry and outbox workers drain bounded batches
with `FOR UPDATE SKIP LOCKED`, so multiple instances never double-process; the
outbox gives at-least-once delivery to idempotent consumers.

**9. Test strategy (30s).** 99 tests against **real PostgreSQL** — unit (incl.
Hypothesis property tests), API, integration (constraints, migrations up/down),
and genuinely-concurrent tests via `asyncio.gather`. 92% coverage overall, 93% on
core domain/services.

**10. Load-test findings (30s).** Benchmarking surfaced synchronous bcrypt
blocking the event loop; moving it to a thread cut login p50 from ~5.7s to ~0.69s
and read p50 from ~2.7s to ~0.06s.

**11. Deployment (20s).** Non-root Docker image, Compose with a migration job and
health checks, CI running lint/type/tests/build. Honest status: not yet deployed;
Docker wasn't available on the build machine, so everything was verified against a
local PostgreSQL instead.

**12. At millions-of-users scale (25s).** Stateless API replicas behind a load
balancer; read replicas + caching for search; per-slot write contention is the
real limit → sharded counters or a queue for flash-sale slots; a real message bus
for the outbox with a DLQ; rate limiting; distributed tracing.

## Likely questions & answer points

- **How exactly do you prevent overselling?** Row lock serializes writers per
  slot; CHECK constraint is the hard backstop; both are covered by a concurrency
  test that fails on regression.
- **Why not `SERIALIZABLE`?** It's correct but forces retry-on-`40001`; row locks
  give the same guarantee without client-visible retries on the hot path.
- **What if two identical requests arrive at the same instant with one key?** The
  unique `(key, endpoint, actor)` constraint lets one commit; the other rolls back
  its whole transaction and replays the stored response — so no double effect.
- **Exactly-once webhook processing?** At the DB level yes for *recording* (unique
  `event_id`); delivery to downstream is at-least-once, hence idempotent consumers.
- **Why Decimal?** Floats can't represent money exactly; Decimal + per-currency
  minor units avoids drift; property-tested.
- **What breaks first under load?** A single hot slot's write throughput (writes
  serialize on its row) — measured behaviour, and the documented next step is
  sharded counters/queueing.
- **Biggest thing you'd change?** Wire the outbox to a real bus with a DLQ and add
  a repeatable multi-worker load rig.
