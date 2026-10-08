"""Smoke test: verifies the real-Postgres harness and core happy path wire up."""

from __future__ import annotations

import uuid

import pytest

from tests.factories import auth_header, seed_customer_slot

pytestmark = pytest.mark.api


async def test_health_live(client) -> None:
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


async def test_health_ready_ok(client) -> None:
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


async def test_reservation_happy_path(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session, capacity=5)
    resp = await client.post(
        "/api/v1/reservations",
        json={"slot_id": str(slot.id), "quantity": 2},
        headers={**auth_header(customer), "Idempotency-Key": uuid.uuid4().hex},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["quantity"] == 2
    assert body["total_price"] == "160.00"
    assert body["status"] == "active"
