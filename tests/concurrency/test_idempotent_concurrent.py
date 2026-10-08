"""Concurrency: the same idempotency key never creates two reservations."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from app.models.reservation import Reservation
from tests.factories import auth_header, seed_customer_slot

pytestmark = pytest.mark.concurrency

CONCURRENT = 10


async def test_concurrent_same_key_creates_one_reservation(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session, capacity=5)
    key = uuid.uuid4().hex
    body = {"slot_id": str(slot.id), "quantity": 1}
    headers = {**auth_header(customer), "Idempotency-Key": key}

    async def reserve() -> tuple[int, str | None]:
        resp = await client.post("/api/v1/reservations", json=body, headers=headers)
        return resp.status_code, resp.json().get("id")

    results = await asyncio.gather(*(reserve() for _ in range(CONCURRENT)))

    # Every response is a success referring to the SAME reservation id.
    ids = {rid for _status, rid in results if rid}
    assert len(ids) == 1, f"expected one reservation id, saw {ids}"
    assert all(status in (200, 201) for status, _ in results)

    # Exactly one reservation row; only one unit of inventory consumed.
    reservation_count = await db_session.scalar(
        select(func.count()).select_from(Reservation).where(Reservation.slot_id == slot.id)
    )
    assert reservation_count == 1

    await db_session.refresh(slot)
    assert slot.reserved_quantity == 1
