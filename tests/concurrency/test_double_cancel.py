"""Concurrency: duplicate cancellations restore inventory exactly once."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from tests.factories import auth_header, seed_customer_slot

pytestmark = pytest.mark.concurrency

CONCURRENT = 10


async def test_no_double_restoration(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session, capacity=5)
    reservation = (
        await client.post(
            "/api/v1/reservations",
            json={"slot_id": str(slot.id), "quantity": 3},
            headers={**auth_header(customer), "Idempotency-Key": uuid.uuid4().hex},
        )
    ).json()
    booking = (
        await client.post(
            "/api/v1/bookings",
            json={"reservation_id": reservation["id"]},
            headers={**auth_header(customer), "Idempotency-Key": uuid.uuid4().hex},
        )
    ).json()

    await db_session.refresh(slot)
    assert slot.confirmed_quantity == 3

    async def cancel() -> int:
        resp = await client.post(
            f"/api/v1/bookings/{booking['id']}/cancel", headers=auth_header(customer)
        )
        return resp.status_code

    statuses = await asyncio.gather(*(cancel() for _ in range(CONCURRENT)))
    # Every concurrent cancel is safe (idempotent) — all succeed.
    assert all(s == 200 for s in statuses)

    # Inventory restored exactly once: confirmed back to 0, never negative.
    await db_session.refresh(slot)
    assert slot.confirmed_quantity == 0
    assert slot.reserved_quantity == 0
