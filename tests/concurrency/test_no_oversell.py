"""Concurrency: the flagship overselling-prevention proof.

Capacity 5, 20 concurrent single-unit reservation requests → exactly 5 succeed,
15 receive a deterministic inventory-conflict (409), and the slot's counters
remain consistent. Requests run truly concurrently via ``asyncio.gather`` against
real PostgreSQL, each on its own connection.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from app.domain.enums import ReservationStatus
from app.models.reservation import Reservation
from tests.factories import auth_header, seed_customer_slot

pytestmark = pytest.mark.concurrency

CAPACITY = 5
CONCURRENT_REQUESTS = 20


async def test_no_overselling_under_concurrency(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session, capacity=CAPACITY)
    headers_base = auth_header(customer)

    async def reserve_one() -> int:
        resp = await client.post(
            "/api/v1/reservations",
            json={"slot_id": str(slot.id), "quantity": 1},
            headers={**headers_base, "Idempotency-Key": uuid.uuid4().hex},
        )
        return resp.status_code

    statuses = await asyncio.gather(*(reserve_one() for _ in range(CONCURRENT_REQUESTS)))

    successes = sum(1 for s in statuses if s == 201)
    conflicts = sum(1 for s in statuses if s == 409)

    assert successes == CAPACITY, f"expected {CAPACITY} successes, got {successes}"
    assert conflicts == CONCURRENT_REQUESTS - CAPACITY
    assert successes + conflicts == CONCURRENT_REQUESTS  # no other status codes

    # Database counters must exactly reflect the successful reservations.
    await db_session.refresh(slot)
    assert slot.reserved_quantity == CAPACITY
    assert slot.confirmed_quantity == 0
    assert slot.reserved_quantity + slot.confirmed_quantity <= slot.capacity

    active = await db_session.scalar(
        select(func.count())
        .select_from(Reservation)
        .where(
            Reservation.slot_id == slot.id,
            Reservation.status == ReservationStatus.ACTIVE,
        )
    )
    assert active == CAPACITY
