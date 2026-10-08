# ADR 0006 — JWT access tokens and role-based authorization

**Status:** Accepted · **Context:** independent portfolio project (not Klook).

## Context
The API needs authentication and coarse authorization (customer / merchant /
admin) plus per-resource ownership checks, without overbuilding account
management.

## Decision
Use **short-lived JWT (HS256) bearer tokens** issued at login. Passwords are
hashed with **bcrypt**. Role dependencies gate endpoints; **services enforce
per-resource ownership** (e.g. a customer may only confirm their own reservation;
a merchant may only edit their own slots). Secrets come from environment
variables; none are committed.

## Consequences
- Stateless auth: tokens are validated from claims, no session store, so API
  replicas need no shared state.
- Token lifetime is short; there is intentionally no refresh/rotation,
  registration, or social login (out of scope).
- bcrypt is CPU-heavy; it is run in a worker thread (`asyncio.to_thread`) so it
  does not block the event loop under concurrent logins (see the load-test
  report).

## Alternatives considered
- **Server-side sessions:** require shared session storage; unnecessary here.
- **OAuth/OIDC provider:** appropriate for production SSO but far beyond this
  project's scope.
