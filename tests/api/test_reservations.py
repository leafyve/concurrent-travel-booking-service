"""API tests for reservation creation and idempotency."""

from __future__ import annotations

import uuid

import pytest

from app.domain.enums import UserRole
from tests.factories import auth_header, create_user, seed_customer_slot

pytestmark = pytest.mark.api


def _headers(customer, key=None):
    return {**auth_header(customer), "Idempotency-Key": key or uuid.uuid4().hex}


async def test_create_reservation(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session, capacity=5)
    resp = await client.post(
        "/api/v1/reservations",
        json={"slot_id": str(slot.id), "quantity": 2},
        headers=_headers(customer),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["quantity"] == 2
    assert body["status"] == "active"
    assert resp.headers["Idempotent-Replayed"] == "false"


async def test_missing_idempotency_key_is_400(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session)
    resp = await client.post(
        "/api/v1/reservations",
        json={"slot_id": str(slot.id), "quantity": 1},
        headers=auth_header(customer),
    )
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "bad_request"


async def test_idempotent_replay_same_key_same_body(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session)
    key = uuid.uuid4().hex
    body = {"slot_id": str(slot.id), "quantity": 1}
    first = await client.post("/api/v1/reservations", json=body, headers=_headers(customer, key))
    second = await client.post("/api/v1/reservations", json=body, headers=_headers(customer, key))
    assert first.json()["id"] == second.json()["id"]
    assert second.headers["Idempotent-Replayed"] == "true"


async def test_idempotency_conflict_same_key_different_body(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session)
    key = uuid.uuid4().hex
    await client.post(
        "/api/v1/reservations",
        json={"slot_id": str(slot.id), "quantity": 1},
        headers=_headers(customer, key),
    )
    conflict = await client.post(
        "/api/v1/reservations",
        json={"slot_id": str(slot.id), "quantity": 2},
        headers=_headers(customer, key),
    )
    assert conflict.status_code == 409
    assert conflict.json()["error_code"] == "idempotency_key_conflict"


async def test_inventory_conflict_when_insufficient(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session, capacity=2)
    resp = await client.post(
        "/api/v1/reservations",
        json={"slot_id": str(slot.id), "quantity": 3},
        headers=_headers(customer),
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "inventory_unavailable"


async def test_reservation_requires_customer_role(client, db_session) -> None:
    _customer, slot = await seed_customer_slot(db_session)
    merchant = await create_user(db_session, role=UserRole.MERCHANT)
    resp = await client.post(
        "/api/v1/reservations",
        json={"slot_id": str(slot.id), "quantity": 1},
        headers=_headers(merchant),
    )
    assert resp.status_code == 403


async def test_reservation_validation_error(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session)
    resp = await client.post(
        "/api/v1/reservations",
        json={"slot_id": str(slot.id), "quantity": 0},  # min is 1
        headers=_headers(customer),
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "validation_failed"
    assert "quantity" in resp.json()["field_errors"]


async def test_reservation_unknown_slot_404(client, db_session) -> None:
    customer, _ = await seed_customer_slot(db_session)
    resp = await client.post(
        "/api/v1/reservations",
        json={"slot_id": str(uuid.uuid4()), "quantity": 1},
        headers=_headers(customer),
    )
    assert resp.status_code == 404
