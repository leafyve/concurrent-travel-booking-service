"""Transactional-outbox processing service (used by the outbox worker).

Reads pending events in bounded batches under ``FOR UPDATE SKIP LOCKED``,
simulates delivery to external consumers (email / notification / analytics), and
records attempt counts and errors. Transient failures stay ``pending`` and are
retried on the next poll until ``outbox_max_attempts``, after which they are
parked as ``failed``.

**Delivery is at-least-once, not exactly-once.** External consumers must be
idempotent (each event payload carries stable ids to enable that).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time import utcnow
from app.domain.enums import OutboxStatus
from app.models.outbox import OutboxEvent
from app.observability.logging import get_logger
from app.observability.metrics import OUTBOX_RETRIES, WORKER_BATCH_DURATION
from app.repositories.outbox_repo import OutboxRepository

# A delivery handler receives an event and either returns (delivered) or raises
# (transient failure → retry).
DeliveryHandler = Callable[[OutboxEvent], Awaitable[None]]

_logger = get_logger("outbox")


async def default_delivery_handler(event: OutboxEvent) -> None:
    """Simulate fan-out to downstream consumers (structured log only)."""
    _logger.info(
        "outbox.delivered",
        event_type=event.event_type,
        aggregate_type=event.aggregate_type,
        aggregate_id=str(event.aggregate_id),
        attempt=event.attempt_count,
    )


@dataclass(frozen=True, slots=True)
class BatchResult:
    processed: int
    retried: int
    failed: int


class OutboxProcessor:
    def __init__(
        self,
        session: AsyncSession,
        *,
        deliver: DeliveryHandler | None = None,
        max_attempts: int | None = None,
    ) -> None:
        self._session = session
        self._repo = OutboxRepository(session)
        self._deliver = deliver or default_delivery_handler
        self._max_attempts = max_attempts or get_settings().outbox_max_attempts

    async def run_batch(self, limit: int) -> BatchResult:
        processed = retried = failed = 0
        with WORKER_BATCH_DURATION.labels("outbox").time():
            events = await self._repo.fetch_pending_for_update(limit)
            for event in events:
                event.attempt_count += 1
                try:
                    await self._deliver(event)
                except Exception as exc:
                    # Not swallowed: we persist the error and re-schedule.
                    event.last_error = str(exc)[:500]
                    OUTBOX_RETRIES.inc()
                    if event.attempt_count >= self._max_attempts:
                        event.status = OutboxStatus.FAILED
                        failed += 1
                    else:
                        retried += 1
                    continue
                event.status = OutboxStatus.PROCESSED
                event.processed_at = utcnow()
                event.last_error = None
                processed += 1
            await self._session.commit()
        return BatchResult(processed=processed, retried=retried, failed=failed)
