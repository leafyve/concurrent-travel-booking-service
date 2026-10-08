"""Integration tests for reservation expiry and inventory release."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.time import utcnow
from app.domain.enums import ReservationStatus
from app.models.outbox import OutboxEvent
from app.models.reservation import Reservation
from app.services.expiry_service import ReservationExpiryService
from tests.factories import seed_customer_slot

pytestmark = pytest.mark.integration


async def _make_expired_reservation(db_session, customer, slot, *, quantity=2):
    reservation = Reservation(
        customer_id=customer.id,
        slot_id=slot.id,
        quantity=quantity,
        unit_price=Decimal("10.00"),
        total_price=Decimal("20.00"),
        currency="SGD",
        status=ReservationStatus.ACTIVE,
        expires_at=utcnow() - timedelta(minutes=1),
    )
    db_session.add(reservation)
    await db_session.commit()
    return reservation


async def test_expiry_releases_inventory_once(sessionmaker_, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session, capacity=5)
    # Simulate a held reservation.
    slot.reserved_quantity = 2
    await db_session.commit()
    reservation = await _make_expired_reservation(db_session, customer, slot, quantity=2)

    async with sessionmaker_() as s:
        expired = await ReservationExpiryService(s).run_batch(50)
    assert expired == 1

    await db_session.refresh(reservation)
    await db_session.refresh(slot)
    assert reservation.status == ReservationStatus.EXPIRED
    assert slot.reserved_quantity == 0

    # An outbox event was emitted.
    count = await db_session.scalar(
        select(func.count())
        .select_from(OutboxEvent)
        .where(OutboxEvent.event_type == "reservation.expired")
    )
    assert count == 1


async def test_expiry_is_idempotent(sessionmaker_, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session, capacity=5)
    slot.reserved_quantity = 1
    await db_session.commit()
    await _make_expired_reservation(db_session, customer, slot, quantity=1)

    async with sessionmaker_() as s:
        assert await ReservationExpiryService(s).run_batch(50) == 1
    # Running again releases nothing (no double restoration).
    async with sessionmaker_() as s:
        assert await ReservationExpiryService(s).run_batch(50) == 0

    await db_session.refresh(slot)
    assert slot.reserved_quantity == 0


async def test_active_reservation_not_expired(sessionmaker_, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session, capacity=5)
    slot.reserved_quantity = 1
    await db_session.commit()
    reservation = Reservation(
        customer_id=customer.id,
        slot_id=slot.id,
        quantity=1,
        unit_price=Decimal("10.00"),
        total_price=Decimal("10.00"),
        currency="SGD",
        status=ReservationStatus.ACTIVE,
        expires_at=utcnow() + timedelta(minutes=30),  # not expired
    )
    db_session.add(reservation)
    await db_session.commit()

    async with sessionmaker_() as s:
        assert await ReservationExpiryService(s).run_batch(50) == 0
    await db_session.refresh(reservation)
    assert reservation.status == ReservationStatus.ACTIVE
