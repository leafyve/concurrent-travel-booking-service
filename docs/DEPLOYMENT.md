# Deployment Runbook

Independent educational portfolio project. Not affiliated with Klook.

> **Current status: NOT deployed.** No external deployment has been performed.
> Docker was not available on the build machine, so `docker build` and
> `docker compose up` have **not** been executed here. The Compose/CI YAML is
> syntactically validated; the application, migrations, seed, workers, demo, and
> benchmark were all verified against a local PostgreSQL. Follow the checklist
> below **only** on infrastructure you own, and do not deploy externally without
> explicit approval.

## Target

A small Linux server (e.g. 1–2 vCPU, 2–4 GB RAM) running Docker + Docker Compose,
with a Caddy reverse proxy terminating HTTPS.

## Assets

- `Dockerfile` — multi-stage, **non-root** runtime, stdlib health check.
- `docker-compose.yml` — `postgres`, one-off `migrate` job, `api`, `worker-expiry`,
  `worker-outbox`, optional `seed`; health checks and `depends_on` conditions;
  `restart: unless-stopped`.
- `deploy/Caddyfile` — HTTPS reverse proxy example (auto Let's Encrypt).

## First deploy (checklist)

1. **Provision** the server; install Docker Engine + Compose plugin.
2. **Secrets**: create a real `.env` (never commit it). At minimum set strong
   `JWT_SECRET` and `WEBHOOK_SIGNING_SECRET` (`openssl rand -hex 32`), and a real
   `DATABASE_URL` password. `.env` is git-ignored.
3. **Bring up data + app**:
   ```bash
   docker compose up --build -d      # postgres → migrate (runs once) → api + workers
   docker compose ps                 # all healthy?
   ```
4. **Seed** (optional, demo only): `docker compose run --rm seed`.
5. **Reverse proxy**: run Caddy with `deploy/Caddyfile` (set your domain + DNS),
   which obtains TLS automatically and proxies to `api:8000`.

## Post-deploy verification (run these and confirm)

- Public health: `curl https://api.example.com/health/ready` → `200 {"status":"ready"}`.
- **HTTPS** valid (padlock; HSTS header present).
- **OpenAPI docs** reachable: `https://api.example.com/docs`.
- **Database persistence**: restart Postgres container; data survives (named
  volume `pgdata`).
- **Workers running**: `docker compose logs worker-expiry worker-outbox` show
  periodic polls.
- **Migration status**: `docker compose run --rm migrate alembic current` matches
  head.
- **Restart recovery**: `docker compose restart api`; `/health/ready` returns
  green.
- **No dev secrets exposed**: `/metrics` not public (blocked at the proxy);
  no secrets in logs; `.env` not in the image (see `.dockerignore`).

## Backups & restore

```bash
# Backup
docker compose exec -T postgres pg_dump -U booking booking | gzip > backup_$(date +%F).sql.gz
# Restore (into an empty DB)
gunzip -c backup_YYYY-MM-DD.sql.gz | docker compose exec -T postgres psql -U booking booking
```

Schedule `pg_dump` via cron; keep off-box copies; test restores periodically.

## Rollback

1. Redeploy the previous image tag (`docker compose up -d` with the pinned tag).
2. If a **migration** must be reverted: `docker compose run --rm migrate alembic
   downgrade -1` (only for backward-compatible steps; verify on a copy first).
3. Health-check and smoke-test (`scripts/demo.py` against the environment) before
   restoring traffic.

## Logs & metrics in production

- Logs are structured JSON on stdout → ship with the container runtime / a log
  agent; filter by `request_id`.
- Scrape `/metrics` from Prometheus **on the private network** (not exposed
  publicly); alert on error rate, p95 latency, `inventory_conflicts_total`
  spikes, and `outbox` backlog/`failed` events.

## Security notes

- Non-root container user; secrets only via environment; `.env` git-ignored and
  excluded from the image.
- Short-lived JWTs; bcrypt password hashing (offloaded from the event loop).
- Webhook endpoint requires a valid HMAC signature and a fresh timestamp.
