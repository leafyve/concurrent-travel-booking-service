# API Contract

Independent educational portfolio project. Not affiliated with Klook.
Base path: `/api/v1`. Interactive docs: `/docs` (Swagger) · `/openapi.json`.

## Authentication

- `POST /api/v1/auth/login` exchanges credentials for a short-lived **JWT**
  (HS256) bearer token. Send it as `Authorization: Bearer <token>`.
- Roles: `customer`, `merchant`, `admin`. Role-gated endpoints return `403` for
  the wrong role; services additionally enforce per-resource ownership.

## Error format (RFC 7807-inspired)

Every error returns `application/problem+json`:

```json
{
  "type": "about:blank",
  "title": "Inventory Unavailable",
  "status": 409,
  "detail": "Only 0 unit(s) available for this slot.",
  "error_code": "inventory_unavailable",
  "request_id": "0cb14c9c6091462485c363f84edbf239",
  "field_errors": { "quantity": "Input should be greater than or equal to 1" }
}
```

`error_code` is stable and machine-readable; `request_id` correlates with logs;
`field_errors` appears on validation failures. Stack traces and DB internals are
never returned.

## Endpoints

### `POST /auth/login`
Body `{ "email", "password" }` → `200 { access_token, token_type, expires_in }`.
`401 unauthenticated` on bad/inactive credentials.

### `GET /auth/me`  *(auth)*
→ `200 { id, email, role, is_active }`. `401` if unauthenticated.

### `GET /experiences`
Query: `destination`, `category`, `starts_from`, `starts_to`,
`min_available_capacity`, `limit` (1–100, default 20), `offset`.
→ `200 { items: [...], total, limit, offset }`. Deterministic ordering; no N+1.

### `GET /experiences/{experience_id}`
→ `200` experience detail · `404 not_found`.

### `GET /experiences/{experience_id}/slots`
Query: `starts_from`, `starts_to`.
→ `200 [ { id, starts_at, ends_at, currency, price, total_capacity,
available_capacity, status } ]`. Internal reservation counters are not exposed.

### `POST /reservations`  *(customer)*  — **idempotent**
Headers: `Authorization`, `Idempotency-Key` (required).
Body `{ "slot_id", "quantity" (1–50) }`.
→ `201` reservation · replay returns the same body with header
`Idempotent-Replayed: true` · `409 inventory_unavailable` · `409
idempotency_key_conflict` (same key, different body) · `400 bad_request` (missing
key) · `404 not_found` (unknown slot) · `422 validation_failed`.

```json
{ "id": "…", "slot_id": "…", "customer_id": "…", "quantity": 2,
  "unit_price": "68.00", "total_price": "136.00", "currency": "SGD",
  "status": "active", "expires_at": "2026-07-25T09:10:00Z", "created_at": "…" }
```

### `POST /bookings`  *(customer)*  — **idempotent**
Headers: `Authorization`, `Idempotency-Key`.
Body `{ "reservation_id" }`.
→ `201` booking (`pending_payment`) · `403 forbidden` (not owner) · `409
reservation_expired` · `409 reservation_not_active` · `409
reservation_already_booked`.

### `GET /bookings/{booking_id}`  *(auth; owner or admin)*
→ `200` booking · `403` · `404`.

### `POST /bookings/{booking_id}/cancel`  *(auth; owner or admin)*  — **idempotent**
→ `200 { booking, refundable, refund_amount, reason }`. Repeated calls are safe
no-ops (inventory restored once).

### `POST /merchant/inventory-updates`  *(merchant)*
Body `{ "external_update_id", "slot_id", "requested_capacity" (0–100000) }`.
→ `200` with `status: accepted|rejected` and a `validation_result`
(rejected when capacity < committed inventory). `403 forbidden` (not your slot /
no merchant account) · `404 not_found`. Duplicate `external_update_id` replays the
stored result.

### `POST /webhooks/payments`  *(signed; no user auth)*
Headers: `X-Webhook-Signature` (hex HMAC-SHA256 of `"{timestamp}.{body}"`),
`X-Webhook-Timestamp`.
Body `{ event_id, type: payment.succeeded|payment.failed, provider_reference,
amount_minor, currency }`.
→ `200 { received, status, detail }` (`processed` | `failed` | `duplicate`) ·
`401 invalid_webhook_signature` · `400 webhook_timestamp_out_of_window` · `409
payment_amount_mismatch` · `404 not_found`.

### Operational (unversioned)
- `GET /health/live` → `200`.
- `GET /health/ready` → `200`/`503` (checks DB).
- `GET /metrics` → Prometheus text.

## Status-code summary

| Code | Meaning |
|------|---------|
| 200 | OK (reads, cancel, webhook, idempotent replay) |
| 201 | Created (reservation, booking) |
| 400 | Bad request (e.g. missing Idempotency-Key, stale webhook) |
| 401 | Unauthenticated / bad webhook signature |
| 403 | Wrong role or not the resource owner |
| 404 | Resource not found |
| 409 | Inventory / idempotency / state conflict, amount mismatch |
| 422 | Request validation failed |
| 500 | Unexpected (opaque; logged server-side) |
| 503 | Not ready (DB unavailable) |
