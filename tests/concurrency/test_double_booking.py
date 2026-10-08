"""Concurrency: one reservation can produce at most one booking."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from app.models.booking import Booking
from tests.factories import auth_header, seed_customer_slot

pytestmark = pytest.mark.concurrency

CONCURRENT = 12


async def test_no_double_booking(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session, capacity=5)
    reservation = (
        await client.post(
            "/api/v1/reservations",
            json={"slot_id": str(slot.id), "quantity": 1},
            headers={**auth_header(customer), "Idempotency-Key": uuid.uuid4().hex},
        )
    ).json()

    async def confirm() -> int:
        resp = await client.post(
            "/api/v1/bookings",
            json={"reservation_id": reservation["id"]},
            headers={**auth_header(customer), "Idempotency-Key": uuid.uuid4().hex},
        )
        return resp.status_code

    statuses = await asyncio.gather(*(confirm() for _ in range(CONCURRENT)))
    successes = sum(1 for s in statuses if s == 201)
    conflicts = sum(1 for s in statuses if s == 409)

    assert successes == 1, f"expected exactly one booking, got {successes}"
    assert conflicts == CONCURRENT - 1

    booking_count = await db_session.scalar(
        select(func.count())
        .select_from(Booking)
        .where(Booking.reservation_id == uuid.UUID(reservation["id"]))
    )
    assert booking_count == 1

    await db_session.refresh(slot)
    assert slot.confirmed_quantity == 1
    assert slot.reserved_quantity == 0
