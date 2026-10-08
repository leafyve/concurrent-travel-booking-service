"""Integration tests: database constraints are the last line of defence.

These assert that PostgreSQL itself rejects impossible states, independent of any
application-level check.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.time import utcnow
from app.domain.enums import BookingStatus, PaymentStatus, ReservationStatus
from app.models.booking import Booking, PaymentAttempt
from app.models.idempotency import IdempotencyRecord
from app.models.reservation import Reservation
from tests.factories import seed_customer_slot

pytestmark = pytest.mark.integration


async def _update_expecting_integrity_error(sessionmaker_, sql, params) -> None:
    async with sessionmaker_() as s:
        with pytest.raises(IntegrityError):
            await s.execute(text(sql), params)
            await s.commit()


async def test_reserved_quantity_cannot_be_negative(sessionmaker_, db_session) -> None:
    _c, slot = await seed_customer_slot(db_session)
    await _update_expecting_integrity_error(
        sessionmaker_,
        "UPDATE experience_slots SET reserved_quantity = -1 WHERE id = :id",
        {"id": slot.id},
    )


async def test_confirmed_quantity_cannot_be_negative(sessionmaker_, db_session) -> None:
    _c, slot = await seed_customer_slot(db_session)
    await _update_expecting_integrity_error(
        sessionmaker_,
        "UPDATE experience_slots SET confirmed_quantity = -1 WHERE id = :id",
        {"id": slot.id},
    )


async def test_committed_cannot_exceed_capacity(sessionmaker_, db_session) -> None:
    _c, slot = await seed_customer_slot(db_session, capacity=5)
    await _update_expecting_integrity_error(
        sessionmaker_,
        "UPDATE experience_slots SET reserved_quantity = 6 WHERE id = :id",
        {"id": slot.id},
    )


async def test_reservation_quantity_must_be_positive(sessionmaker_, db_session) -> None:
    _c, slot = await seed_customer_slot(db_session)
    async with sessionmaker_() as s:
        reservation = Reservation(
            customer_id=_c.id,
            slot_id=slot.id,
            quantity=0,  # violates ck_reservations_quantity_positive
            unit_price=Decimal("10.00"),
            total_price=Decimal("0.00"),
            currency="SGD",
            status=ReservationStatus.ACTIVE,
            expires_at=utcnow() + timedelta(minutes=10),
        )
        s.add(reservation)
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_unique_idempotency_scope(sessionmaker_) -> None:
    actor = uuid.uuid4()

    def _record() -> IdempotencyRecord:
        return IdempotencyRecord(
            idempotency_key="dup-key",
            actor_id=actor,
            endpoint="POST /x",
            request_fingerprint="abc",
            response_status=201,
            response_body={"ok": True},
            expires_at=utcnow() + timedelta(hours=1),
            created_at=utcnow(),
        )

    async with sessionmaker_() as s:
        s.add(_record())
        await s.commit()
    async with sessionmaker_() as s:
        s.add(_record())
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_unique_payment_event_id(sessionmaker_, db_session) -> None:
    _c, slot = await seed_customer_slot(db_session)
    # Build a minimal reservation + booking to satisfy the FK.
    async with sessionmaker_() as s:
        reservation = Reservation(
            customer_id=_c.id,
            slot_id=slot.id,
            quantity=1,
            unit_price=Decimal("10.00"),
            total_price=Decimal("10.00"),
            currency="SGD",
            status=ReservationStatus.CONVERTED,
            expires_at=utcnow() + timedelta(minutes=10),
        )
        s.add(reservation)
        await s.flush()
        booking = Booking(
            booking_reference=f"BKG-{uuid.uuid4().hex[:8].upper()}",
            reservation_id=reservation.id,
            customer_id=_c.id,
            slot_id=slot.id,
            quantity=1,
            total_price=Decimal("10.00"),
            currency="SGD",
            status=BookingStatus.PENDING_PAYMENT,
        )
        s.add(booking)
        await s.flush()
        s.add(
            PaymentAttempt(
                booking_id=booking.id,
                provider_reference="pi_x",
                amount=Decimal("10.00"),
                currency="SGD",
                status=PaymentStatus.SUCCEEDED,
                event_id="evt_dup",
            )
        )
        await s.commit()
        booking_id = booking.id

    async with sessionmaker_() as s:
        s.add(
            PaymentAttempt(
                booking_id=booking_id,
                provider_reference="pi_x",
                amount=Decimal("10.00"),
                currency="SGD",
                status=PaymentStatus.SUCCEEDED,
                event_id="evt_dup",  # duplicate event id
            )
        )
        with pytest.raises(IntegrityError):
            await s.commit()
