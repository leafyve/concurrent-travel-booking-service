# Recruiter Demo (~3 minutes)

Independent educational portfolio project. Not affiliated with Klook.
A short, reproducible demo that shows the system's core guarantees.

## Setup (once)

**With Docker:**
```bash
docker compose up --build -d
docker compose run --rm seed
```

**Without Docker (local venv + local PostgreSQL):**
```bash
pip install -e ".[dev,load]"
alembic upgrade head
python -m scripts.seed
python -m scripts.run_api            # leave running in one terminal
```

## The 3-minute script

Run the automated lifecycle demo in a second terminal — it performs every step
below and **fails loudly if any invariant is violated**:

```bash
python -m scripts.demo
```

Expected output (abridged, from an actual run):
```
✓ Logged in as customer.alice@demo.test
✓ Selected slot … (available=12)
✓ Reservation created: … total=1500.00 THB
✓ Idempotent retry returned the same reservation (no duplicate)
✓ Same key + different payload correctly rejected with 409
✓ Booking confirmed (pending payment): BKG-…
✓ Payment webhook processed (booking confirmed)
✓ Replayed webhook safely deduplicated
✓ Booking is CONFIRMED
✓ Booking cancelled (refundable=True)
✓ Duplicate cancellation handled idempotently
✓ Inventory restored exactly once (available back to 12)
All lifecycle invariants held. Demo succeeded. ✅
```

### What each step proves
1. **Log in** → JWT auth works.
2. **View a limited-capacity slot** → availability read (internal counters hidden).
3. **Create a reservation** → concurrency-safe inventory hold.
4. **Retry with the same Idempotency-Key** → no duplicate (same reservation id).
5. **Confirm the booking** → reserved converts to confirmed, one booking.
6. **Send a signed payment webhook** → HMAC-verified, booking confirmed.
7. **Replay the webhook** → deduplicated (no double effect).
8. **No duplicate booking** → confirmed booking looked up successfully.
9. **Run the overselling test** (headline evidence):
   ```bash
   pytest tests/concurrency/test_no_oversell.py -q   # cap 5, 20 concurrent → exactly 5
   ```
10. **Show logs, metrics, results:**
    ```bash
    curl -s localhost:8000/metrics | grep -E 'reservations_created_total|inventory_conflicts_total'
    curl -s localhost:8000/health/ready
    ```

## Talking points (30 seconds)

"The database is the source of truth for inventory. A row lock plus a check
constraint make overselling impossible, idempotency keys make retries safe, and
signed webhooks with event dedup make payments safe to replay. All of that is
proven by tests that run real concurrent requests against real PostgreSQL."

## Seeded demo accounts (local only)
`admin@demo.test`, `merchant.marina@demo.test`, `merchant.eastasia@demo.test`,
`customer.alice@demo.test`, `customer.ben@demo.test` — password `Password123!`.
Fictional; local demonstration only.
