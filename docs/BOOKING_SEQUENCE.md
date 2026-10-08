# Booking Sequence Diagrams

Independent educational portfolio project. Not affiliated with Klook.

## 1. Reservation creation (idempotent, concurrency-safe)

```mermaid
sequenceDiagram
    actor C as Customer
    participant API as POST /reservations
    participant IS as IdempotencyService
    participant RS as ReservationService
    participant DB as PostgreSQL

    C->>API: slot_id, quantity, Idempotency-Key
    API->>IS: execute(key, endpoint, actor, payload, op)
    IS->>DB: SELECT idempotency_record (key, endpoint, actor)
    alt record exists
        IS-->>API: replay stored response (or 409 if payload differs)
    else fresh
        IS->>RS: op()
        RS->>DB: SELECT slot FOR UPDATE
        alt available >= quantity
            RS->>DB: UPDATE slot.reserved += quantity
            RS->>DB: INSERT reservation (status=active, expires_at)
            RS->>DB: INSERT outbox_event(reservation.created)
            IS->>DB: INSERT idempotency_record
            IS->>DB: COMMIT
            IS-->>API: 201 reservation
        else insufficient
            RS-->>API: 409 inventory_unavailable (rollback)
        end
    end
```

## 2. Booking confirmation (reserved → confirmed, one per reservation)

```mermaid
sequenceDiagram
    actor C as Customer
    participant API as POST /bookings
    participant BS as BookingService
    participant DB as PostgreSQL

    C->>API: reservation_id, Idempotency-Key
    API->>BS: confirm()
    BS->>DB: SELECT reservation FOR UPDATE
    alt not owner / not active / expired / already converted
        BS-->>API: 403 / 409 (deterministic)
    else active & owned
        BS->>DB: SELECT slot FOR UPDATE
        BS->>DB: UPDATE slot: reserved -= q, confirmed += q
        BS->>DB: UPDATE reservation.status = converted
        BS->>DB: INSERT booking (UNIQUE reservation_id)
        BS->>DB: INSERT payment_attempt (pending)
        BS->>DB: INSERT outbox_event(booking.created)
        BS->>DB: COMMIT
        BS-->>API: 201 booking (pending_payment)
    end
```

## 3. Payment webhook (HMAC + replay window + dedup + amount match)

```mermaid
sequenceDiagram
    participant P as Payment provider (simulated)
    participant API as POST /webhooks/payments
    participant PS as PaymentWebhookService
    participant DB as PostgreSQL

    P->>API: raw body + X-Webhook-Signature + X-Webhook-Timestamp
    API->>PS: process(raw_body, timestamp, signature)
    PS->>PS: verify HMAC (constant-time)
    alt bad signature
        PS-->>API: 401 invalid_webhook_signature
    else timestamp outside window
        PS-->>API: 400 webhook_timestamp_out_of_window
    else valid
        PS->>DB: SELECT payment_attempt WHERE event_id = ?
        alt already seen
            PS-->>API: 200 duplicate (no-op)
        else new
            PS->>DB: find booking by provider_reference; SELECT booking FOR UPDATE
            alt amount/currency mismatch
                PS-->>API: 409 payment_amount_mismatch
            else match & succeeded
                PS->>DB: INSERT payment_attempt(event_id UNIQUE, succeeded)
                PS->>DB: UPDATE booking.status = confirmed
                PS->>DB: INSERT outbox_event(booking.confirmed)
                PS->>DB: COMMIT
                PS-->>API: 200 processed
            end
        end
    end
```

## 4. Cancellation (idempotent, restores inventory exactly once)

```mermaid
sequenceDiagram
    actor C as Customer/Admin
    participant API as POST /bookings/{id}/cancel
    participant BS as BookingService
    participant DB as PostgreSQL

    C->>API: booking_id
    API->>BS: cancel()
    BS->>DB: SELECT booking FOR UPDATE
    alt not owner/admin
        BS-->>API: 403
    else already cancelled
        BS-->>API: 200 (idempotent no-op, no re-restore)
    else holds inventory
        BS->>DB: SELECT slot FOR UPDATE
        BS->>DB: UPDATE slot.confirmed -= quantity
        BS->>BS: evaluate cancellation policy (refund?)
        BS->>DB: UPDATE booking.status = cancelled, cancelled_at = now
        BS->>DB: INSERT audit_event + outbox_event(booking.cancelled)
        BS->>DB: COMMIT
        BS-->>API: 200 { refundable, refund_amount, reason }
    end
```

## 5. Reservation expiry (background worker, batched, safe for parallel workers)

```mermaid
sequenceDiagram
    participant W as Expiry worker
    participant DB as PostgreSQL

    loop every poll interval
        W->>DB: SELECT reservations WHERE status=active AND expires_at<=now()<br/>FOR UPDATE SKIP LOCKED LIMIT batch
        alt batch non-empty
            loop each reservation
                W->>DB: SELECT slot FOR UPDATE
                W->>DB: UPDATE slot.reserved -= quantity
                W->>DB: UPDATE reservation.status = expired
                W->>DB: INSERT outbox_event(reservation.expired)
            end
            W->>DB: COMMIT
        else empty
            W->>W: sleep(poll interval)
        end
    end
```
