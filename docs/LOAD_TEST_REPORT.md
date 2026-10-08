# Load Test Report

Independent educational portfolio project. Not affiliated with Klook.
**These are environment-specific local figures, not Klook-scale claims.**

## Machine & environment

| Item | Value |
|------|-------|
| CPU | Intel Core i9-13900H (14 cores / 20 threads) |
| RAM | 32 GB |
| OS | Windows 11 |
| Python | 3.12.10 |
| PostgreSQL | 16.4, local, single instance |
| App server | single Uvicorn worker (`scripts.run_api`) |
| Tool | Locust 2.46 |

## Dataset

Seeded fictional data (`python -m scripts.seed`): 5 users, 5 experiences, 45
slots, 2 pre-existing bookings.

## Command

```bash
locust -f load_tests/locustfile.py --host http://127.0.0.1:8000 \
    --users 50 --spawn-rate 25 --run-time 30s --headless
```

## Endpoint mix

Read-heavy, mirroring real browse traffic: `GET /experiences` (search) and slot
availability dominate; `POST /reservations` (write) is a minority; each virtual
user logs in once.

## Results

### Run B — after fixing the bottleneck (representative)

| Metric | Value |
|--------|-------|
| Total requests (30s) | 4,678 |
| Aggregate throughput | **~158 req/s** |
| Aggregate latency | **p50 8 ms · p95 86 ms · p99 340 ms** |
| `GET /experiences?destination` | 79.8 req/s · p50 7 ms · p95 44 ms |
| `GET /experiences` (availability) | 40.6 req/s · p50 8 ms · p95 58 ms |
| `POST /auth/login` | p50 690 ms (bcrypt cost) |
| `POST /reservations` | p50 9 ms |

### Run A — before the fix

| Metric | Value |
|--------|-------|
| Aggregate throughput | ~107 req/s |
| `POST /auth/login` | **p50 ~5,700 ms** |
| `GET /experiences` | p50 ~2,700 ms |
| Aggregate p99 | ~5,400 ms |

## Bottleneck observation & fix

**Finding:** synchronous **bcrypt** password verification ran on the single
async event-loop thread. Under a burst of concurrent logins, bcrypt (deliberately
CPU-expensive) blocked the loop, so *all* requests — including unrelated reads —
stalled for seconds.

**Fix:** move password verification off the event loop with
`asyncio.to_thread(verify_password, …)` (`app/services/auth_service.py`), letting
the thread pool run bcrypt across cores while the loop keeps serving requests.

**Effect (measured):**

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Login p50 | ~5,700 ms | ~690 ms | ~8× faster |
| `GET /experiences` p50 | ~2,700 ms | ~63 ms | ~40× faster |
| Aggregate throughput | ~107 req/s | ~158 req/s | +48% |
| Aggregate p99 | ~5,400 ms | ~340 ms | ~16× lower |

## Note on "failures"

Locust reports `POST /reservations` as failing with `409` once the small seeded
slot's capacity is exhausted. **These 409s are correct behaviour** — the system
refusing to oversell — not errors. They demonstrate the inventory guard under
load rather than a defect.

## Limitations

- Single Uvicorn worker; no horizontal scaling or multi-worker tuning measured.
- Small seeded dataset; the write path saturates a single hot slot quickly.
- Client and server on the same machine; no network latency modelled.
- Figures are indicative of *relative* behaviour and the fix's impact, not
  absolute capacity planning.
