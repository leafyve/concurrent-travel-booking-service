"""API tests for booking confirmation, lookup, and cancellation."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import update

from app.core.time import utcnow
from app.domain.enums import UserRole
from app.models.reservation import Reservation
from tests.factories import auth_header, create_user, seed_customer_slot

pytestmark = pytest.mark.api


def _hdr(user, key=None):
    return {**auth_header(user), "Idempotency-Key": key or uuid.uuid4().hex}


async def _reserve(client, customer, slot, quantity=1):
    resp = await client.post(
        "/api/v1/reservations",
        json={"slot_id": str(slot.id), "quantity": quantity},
        headers=_hdr(customer),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_confirm_booking(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session)
    reservation = await _reserve(client, customer, slot)
    resp = await client.post(
        "/api/v1/bookings",
        json={"reservation_id": reservation["id"]},
        headers=_hdr(customer),
    )
    assert resp.status_code == 201, resp.text
    booking = resp.json()
    assert booking["status"] == "pending_payment"
    assert booking["booking_reference"].startswith("BKG-")


async def test_booking_idempotent_replay(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session)
    reservation = await _reserve(client, customer, slot)
    key = uuid.uuid4().hex
    body = {"reservation_id": reservation["id"]}
    first = await client.post("/api/v1/bookings", json=body, headers=_hdr(customer, key))
    second = await client.post("/api/v1/bookings", json=body, headers=_hdr(customer, key))
    assert first.json()["id"] == second.json()["id"]
    assert second.headers["Idempotent-Replayed"] == "true"


async def test_reservation_cannot_be_double_booked(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session)
    reservation = await _reserve(client, customer, slot)
    await client.post(
        "/api/v1/bookings",
        json={"reservation_id": reservation["id"]},
        headers=_hdr(customer),
    )
    # Different idempotency key, same reservation → duplicate booking rejected.
    resp = await client.post(
        "/api/v1/bookings",
        json={"reservation_id": reservation["id"]},
        headers=_hdr(customer),
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "reservation_already_booked"


async def test_cannot_confirm_others_reservation(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session)
    reservation = await _reserve(client, customer, slot)
    other = await create_user(db_session, role=UserRole.CUSTOMER)
    resp = await client.post(
        "/api/v1/bookings",
        json={"reservation_id": reservation["id"]},
        headers=_hdr(other),
    )
    assert resp.status_code == 403


async def test_cannot_confirm_expired_reservation(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session)
    reservation = await _reserve(client, customer, slot)
    # Force expiry in the past.
    await db_session.execute(
        update(Reservation)
        .where(Reservation.id == uuid.UUID(reservation["id"]))
        .values(expires_at=utcnow().replace(year=2000))
    )
    await db_session.commit()
    resp = await client.post(
        "/api/v1/bookings",
        json={"reservation_id": reservation["id"]},
        headers=_hdr(customer),
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "reservation_expired"


async def test_get_booking_owner_and_stranger(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session)
    reservation = await _reserve(client, customer, slot)
    booking = (
        await client.post(
            "/api/v1/bookings",
            json={"reservation_id": reservation["id"]},
            headers=_hdr(customer),
        )
    ).json()

    owner_view = await client.get(
        f"/api/v1/bookings/{booking['id']}", headers=auth_header(customer)
    )
    assert owner_view.status_code == 200

    stranger = await create_user(db_session, role=UserRole.CUSTOMER)
    stranger_view = await client.get(
        f"/api/v1/bookings/{booking['id']}", headers=auth_header(stranger)
    )
    assert stranger_view.status_code == 403


async def test_cancel_restores_inventory(client, db_session) -> None:
    customer, slot = await seed_customer_slot(db_session, capacity=5)
    reservation = await _reserve(client, customer, slot, quantity=2)
    booking = (
        await client.post(
            "/api/v1/bookings",
            json={"reservation_id": reservation["id"]},
            headers=_hdr(customer),
        )
    ).json()

    resp = await client.post(
        f"/api/v1/bookings/{booking['id']}/cancel", headers=auth_header(customer)
    )
    assert resp.status_code == 200
    assert resp.json()["booking"]["status"] == "cancelled"

    await db_session.refresh(slot)
    assert slot.confirmed_quantity == 0
    assert slot.reserved_quantity == 0
