# ADR 0003 — Transactional outbox for domain events

**Status:** Accepted · **Context:** independent portfolio project (not Klook).

## Context
Business operations should emit domain events (reservation created, booking
confirmed/cancelled, inventory updated) to downstream consumers (email,
notifications, analytics). Writing to the DB and publishing to a bus in two steps
risks inconsistency: the DB commit succeeds but the publish fails (or vice-versa).

## Decision
Use the **transactional outbox pattern**. Domain events are inserted into an
`outbox_events` table **in the same transaction** as the state change. A separate
**outbox worker** reads pending events under `FOR UPDATE SKIP LOCKED`, "delivers"
them (simulated here), and marks them processed, retrying transient failures.

## Consequences
- The event is persisted atomically with the state change — no lost or phantom
  events.
- Delivery is **at-least-once**, not exactly-once: a crash after delivery but
  before marking processed re-delivers. **Consumers must be idempotent**; event
  payloads carry stable ids to enable that. This is documented for consumers.
- Failed events accumulate `attempt_count`/`last_error` and are parked as
  `failed` after a max-attempts threshold.

## Alternatives considered
- **Dual write (DB then bus):** simplest but not atomic → inconsistency.
- **Change Data Capture (Debezium):** robust but heavy operationally; unjustified
  at this scope.
