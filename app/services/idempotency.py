"""Idempotency orchestration.

Guarantees that a mutating operation runs **at most once** per idempotency key,
and that retries return the identical stored response. Correctness relies on a
UNIQUE constraint over ``(idempotency_key, endpoint, actor_id)``:

* The business operation and the idempotency record are written in **one
  transaction**. If two concurrent requests share a key, exactly one commits;
  the other hits the unique violation, rolls back its *entire* transaction
  (including any duplicate reservation/booking it created) and replays the
  winner's stored response.
* A retry with the *same* payload replays the stored response.
* A retry with a *different* payload for the same key returns **409**.

Only successful responses are stored, so a transient failure (e.g. no capacity)
can be legitimately retried later.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.domain.errors import IdempotencyConflictError
from app.domain.fingerprint import request_fingerprint
from app.models.idempotency import IdempotencyRecord
from app.repositories.idempotency_repo import IdempotencyRepository

IDEMPOTENCY_RECORD_TTL = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class IdempotentResult:
    """The outcome to return to the client (fresh or replayed)."""

    status_code: int
    body: dict[str, Any]
    replayed: bool = False


# An operation performs its work on the session (WITHOUT committing) and returns
# the (status_code, JSON-serialisable body) to persist and return.
Operation = Callable[[], Awaitable[tuple[int, dict[str, Any]]]]


class IdempotencyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = IdempotencyRepository(session)

    async def execute(
        self,
        *,
        key: str,
        endpoint: str,
        actor_id: uuid.UUID,
        request_payload: Any,
        operation: Operation,
    ) -> IdempotentResult:
        fingerprint = request_fingerprint(request_payload)

        existing = await self._repo.get(key=key, endpoint=endpoint, actor_id=actor_id)
        if existing is not None:
            return self._replay(existing, fingerprint)

        # No record yet: run the operation and attempt to claim the key in the
        # same transaction.
        status_code, body = await operation()
        record = IdempotencyRecord(
            idempotency_key=key,
            actor_id=actor_id,
            endpoint=endpoint,
            request_fingerprint=fingerprint,
            response_status=status_code,
            response_body=body,
            expires_at=utcnow() + IDEMPOTENCY_RECORD_TTL,
            created_at=utcnow(),
        )
        self._repo.add(record)
        try:
            await self._session.commit()
        except IntegrityError:
            # Lost the race (or a duplicate constraint fired): discard our work
            # and replay whatever the winner committed.
            await self._session.rollback()
            winner = await self._repo.get(key=key, endpoint=endpoint, actor_id=actor_id)
            if winner is None:
                raise
            return self._replay(winner, fingerprint)
        return IdempotentResult(status_code=status_code, body=body)

    @staticmethod
    def _replay(record: IdempotencyRecord, fingerprint: str) -> IdempotentResult:
        if record.request_fingerprint != fingerprint:
            raise IdempotencyConflictError(
                "This idempotency key was already used with a different request.",
            )
        return IdempotentResult(
            status_code=record.response_status,
            body=record.response_body,
            replayed=True,
        )
