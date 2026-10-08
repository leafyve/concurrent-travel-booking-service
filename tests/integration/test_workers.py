"""Integration tests for the worker entrypoints (run-once mode).

These exercise the worker runner/loop glue against the app's own engine, then
dispose it so later tests keep their per-test engines isolated.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.time import utcnow
from app.db.session import dispose_engine
from app.domain.enums import OutboxStatus, ReservationStatus
from app.models.outbox import OutboxEvent
from app.models.reservation import Reservation
from app.services.events import enqueue_event
from app.workers import expiry, outbox
from tests.factories import seed_customer_slot

pytestmark = pytest.mark.integration


async def test_expiry_worker_run_once(db_session) -> None:
    customer, slot = await seed_customer_slot(db_session, capacity=5)
    slot.reserved_quantity = 1
    await db_session.commit()
    db_session.add(
        Reservation(
            customer_id=customer.id,
            slot_id=slot.id,
            quantity=1,
            unit_price=Decimal("10.00"),
            total_price=Decimal("10.00"),
            currency="SGD",
            status=ReservationStatus.ACTIVE,
            expires_at=utcnow() - timedelta(minutes=1),
        )
    )
    await db_session.commit()

    try:
        expired = await expiry.run(run_once=True)
    finally:
        await dispose_engine()
    assert expired == 1

    await db_session.refresh(slot)
    assert slot.reserved_quantity == 0


async def test_outbox_worker_run_once(db_session) -> None:
    enqueue_event(
        db_session,
        aggregate_type="test",
        aggregate_id=uuid.uuid4(),
        event_type="test.event",
        payload={"x": 1},
    )
    await db_session.commit()

    try:
        handled = await outbox.run(run_once=True)
    finally:
        await dispose_engine()
    assert handled >= 1

    processed = await db_session.scalar(
        select(func.count())
        .select_from(OutboxEvent)
        .where(OutboxEvent.status == OutboxStatus.PROCESSED)
    )
    assert processed >= 1
