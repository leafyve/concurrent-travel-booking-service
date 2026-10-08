"""Integration tests for the transactional outbox and its worker."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.domain.enums import OutboxStatus
from app.models.outbox import OutboxEvent
from app.services.events import enqueue_event
from app.services.outbox_service import OutboxProcessor
from tests.factories import auth_header, seed_customer_slot

pytestmark = pytest.mark.integration


async def test_reservation_writes_outbox_event(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session)
    await client.post(
        "/api/v1/reservations",
        json={"slot_id": str(slot.id), "quantity": 1},
        headers={**auth_header(customer), "Idempotency-Key": uuid.uuid4().hex},
    )
    events = (
        (
            await db_session.execute(
                select(OutboxEvent).where(OutboxEvent.event_type == "reservation.created")
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].status == OutboxStatus.PENDING


async def _seed_events(sessionmaker_, count: int) -> None:
    async with sessionmaker_() as s:
        for i in range(count):
            enqueue_event(
                s,
                aggregate_type="test",
                aggregate_id=uuid.uuid4(),
                event_type="test.event",
                payload={"i": i},
            )
        await s.commit()


async def test_outbox_worker_processes_batch(sessionmaker_) -> None:
    await _seed_events(sessionmaker_, 3)
    async with sessionmaker_() as s:
        result = await OutboxProcessor(s).run_batch(10)
    assert result.processed == 3
    async with sessionmaker_() as s:
        pending = await s.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.PENDING)
        )
    assert pending == 0


async def test_outbox_worker_retries_then_parks_failed(sessionmaker_) -> None:
    await _seed_events(sessionmaker_, 1)

    async def failing(_event: OutboxEvent) -> None:
        raise RuntimeError("simulated transient delivery failure")

    # Attempt 1 and 2 → still pending (retried).
    for _ in range(2):
        async with sessionmaker_() as s:
            result = await OutboxProcessor(s, deliver=failing, max_attempts=3).run_batch(10)
        assert result.retried == 1
        assert result.processed == 0

    async with sessionmaker_() as s:
        event = (await s.execute(select(OutboxEvent))).scalars().one()
        assert event.status == OutboxStatus.PENDING
        assert event.attempt_count == 2
        assert event.last_error

    # Attempt 3 → exhausted, parked as failed.
    async with sessionmaker_() as s:
        result = await OutboxProcessor(s, deliver=failing, max_attempts=3).run_batch(10)
    assert result.failed == 1
    async with sessionmaker_() as s:
        event = (await s.execute(select(OutboxEvent))).scalars().one()
        assert event.status == OutboxStatus.FAILED
        assert event.attempt_count == 3
