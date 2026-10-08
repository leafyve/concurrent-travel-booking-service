"""Concurrency: parallel expiry workers release each reservation exactly once."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.time import utcnow
from app.domain.enums import ReservationStatus
from app.models.reservation import Reservation
from app.services.expiry_service import ReservationExpiryService
from tests.factories import seed_customer_slot

pytestmark = pytest.mark.concurrency

RESERVATIONS = 8


async def test_parallel_expiry_workers_are_safe(sessionmaker_, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session, capacity=RESERVATIONS)
    slot.reserved_quantity = RESERVATIONS
    await db_session.commit()

    for _ in range(RESERVATIONS):
        db_session.add(
            Reservation(
                customer_id=customer.id,
                slot_id=slot.id,
                quantity=1,
                unit_price=Decimal("10.00"),
                total_price=Decimal("10.00"),
                currency="SGD",
                status=ReservationStatus.ACTIVE,
                expires_at=utcnow() - timedelta(minutes=5),
            )
        )
    await db_session.commit()

    async def worker() -> int:
        total = 0
        async with sessionmaker_() as session:
            service = ReservationExpiryService(session)
            # Drain in small batches to force the two workers to interleave.
            while (n := await service.run_batch(3)) > 0:
                total += n
        return total

    results = await asyncio.gather(worker(), worker())

    # Each reservation expired exactly once across both workers.
    assert sum(results) == RESERVATIONS

    await db_session.refresh(slot)
    assert slot.reserved_quantity == 0  # released exactly once, never negative

    still_active = await db_session.scalar(
        select(func.count())
        .select_from(Reservation)
        .where(Reservation.status == ReservationStatus.ACTIVE)
    )
    assert still_active == 0
