# Data Model

Independent educational portfolio project. Not affiliated with Klook.

All primary keys are UUIDs, all timestamps are `TIMESTAMPTZ` (UTC), and all money
is `NUMERIC(12,2)`. Schema is created/managed by Alembic
(`alembic/versions/…_initial_schema.py`).

## Entity–relationship diagram

```mermaid
erDiagram
    USERS ||--o{ MERCHANTS : owns
    USERS ||--o{ RESERVATIONS : makes
    USERS ||--o{ BOOKINGS : holds
    MERCHANTS ||--o{ EXPERIENCES : lists
    EXPERIENCES ||--o{ EXPERIENCE_SLOTS : has
    EXPERIENCE_SLOTS ||--o{ RESERVATIONS : held_by
    EXPERIENCE_SLOTS ||--o{ BOOKINGS : booked_by
    RESERVATIONS ||--|| BOOKINGS : converts_to
    BOOKINGS ||--o{ PAYMENT_ATTEMPTS : paid_by
    MERCHANTS ||--o{ PARTNER_INVENTORY_UPDATES : submits
    EXPERIENCE_SLOTS ||--o{ PARTNER_INVENTORY_UPDATES : targets

    USERS {
        uuid id PK
        string email UK
        string password_hash
        string role
        bool is_active
    }
    MERCHANTS {
        uuid id PK
        uuid owner_user_id FK
        string display_name
        string status
    }
    EXPERIENCES {
        uuid id PK
        uuid merchant_id FK
        string title
        string slug UK
        string destination
        string category
        string currency
        numeric base_price
        string cancellation_policy
        string status
    }
    EXPERIENCE_SLOTS {
        uuid id PK
        uuid experience_id FK
        timestamptz starts_at
        timestamptz ends_at
        int capacity
        int reserved_quantity
        int confirmed_quantity
        int version
        string status
    }
    RESERVATIONS {
        uuid id PK
        uuid customer_id FK
        uuid slot_id FK
        int quantity
        numeric unit_price
        numeric total_price
        string currency
        string status
        timestamptz expires_at
    }
    BOOKINGS {
        uuid id PK
        string booking_reference UK
        uuid reservation_id FK "UNIQUE"
        uuid customer_id FK
        uuid slot_id FK
        int quantity
        numeric total_price
        string status
        timestamptz cancelled_at
    }
    PAYMENT_ATTEMPTS {
        uuid id PK
        uuid booking_id FK
        string provider_reference
        numeric amount
        string currency
        string status
        string event_id "UNIQUE when set"
    }
    IDEMPOTENCY_RECORDS {
        uuid id PK
        string idempotency_key
        uuid actor_id
        string endpoint
        string request_fingerprint
        int response_status
        jsonb response_body
        timestamptz expires_at
    }
    PARTNER_INVENTORY_UPDATES {
        uuid id PK
        uuid merchant_id FK
        string external_update_id
        uuid slot_id FK
        int requested_capacity
        string status
        jsonb validation_result
    }
    OUTBOX_EVENTS {
        uuid id PK
        string aggregate_type
        uuid aggregate_id
        string event_type
        jsonb payload
        string status
        int attempt_count
        string last_error
        timestamptz processed_at
    }
    AUDIT_EVENTS {
        uuid id PK
        uuid actor_id
        string actor_role
        string action
        string entity_type
        uuid entity_id
        jsonb context
    }
```

## Constraints that enforce the invariants

| Constraint | Table | Guarantees |
|------------|-------|------------|
| `CHECK (capacity >= 0)` | experience_slots | Capacity non-negative |
| `CHECK (reserved_quantity >= 0)` | experience_slots | Reserved never negative (inv. 1) |
| `CHECK (confirmed_quantity >= 0)` | experience_slots | Confirmed never negative (inv. 2) |
| `CHECK (reserved + confirmed <= capacity)` | experience_slots | **No overselling** (inv. 3) |
| `CHECK (quantity > 0)` | reservations, bookings | Positive quantities |
| `UNIQUE (reservation_id)` | bookings | **One booking per reservation** (inv. 4) |
| `UNIQUE (booking_reference)` | bookings | Unique human reference |
| `UNIQUE (event_id) WHERE event_id IS NOT NULL` | payment_attempts | **Webhook applied once** (inv. 6) |
| `UNIQUE (idempotency_key, endpoint, actor_id)` | idempotency_records | **One key = one request** (inv. 5) |
| `UNIQUE (merchant_id, external_update_id)` | partner_inventory_updates | Idempotent partner sync |
| Foreign keys (`ON DELETE RESTRICT/CASCADE`) | all relations | Referential integrity |

## Indexes (beyond PKs/uniques)

- `ix_experiences_search (destination, category, status)` — search filter.
- `ix_experience_slots_experience_start (experience_id, starts_at)` — availability.
- `ix_reservations_status_expiry (status, expires_at)` — expiry worker scan.
- `ix_outbox_status_created (status, created_at)` — outbox worker poll.
- `ix_bookings_customer`, `ix_bookings_slot`, `ix_payment_attempts_booking`,
  `ix_audit_entity`, `ix_audit_created`.

The two most load-bearing invariants (no negative inventory; committed ≤ capacity)
are enforced by **PostgreSQL itself**, so they hold even if application code has a
bug — proven in `tests/integration/test_constraints.py`.
