"""Concurrency: parallel outbox workers each process an event exactly once."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from app.domain.enums import OutboxStatus
from app.models.outbox import OutboxEvent
from app.services.events import enqueue_event
from app.services.outbox_service import OutboxProcessor

pytestmark = pytest.mark.concurrency

EVENTS = 20


async def test_parallel_outbox_workers_no_double_processing(sessionmaker_, db_session) -> None:
    async with sessionmaker_() as s:
        for i in range(EVENTS):
            enqueue_event(
                s,
                aggregate_type="test",
                aggregate_id=uuid.uuid4(),
                event_type="test.event",
                payload={"i": i},
            )
        await s.commit()

    async def worker() -> int:
        processed = 0
        async with sessionmaker_() as session:
            processor = OutboxProcessor(session)
            while (result := await processor.run_batch(4)).processed > 0:
                processed += result.processed
        return processed

    results = await asyncio.gather(worker(), worker(), worker())

    # Every event processed exactly once, summed across all workers.
    assert sum(results) == EVENTS

    processed_count = await db_session.scalar(
        select(func.count())
        .select_from(OutboxEvent)
        .where(OutboxEvent.status == OutboxStatus.PROCESSED)
    )
    assert processed_count == EVENTS

    # No event was delivered more than once (attempt_count stays 1 on success).
    max_attempts = await db_session.scalar(select(func.max(OutboxEvent.attempt_count)))
    assert max_attempts == 1
