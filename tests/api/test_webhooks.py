"""API tests for the payment webhook (signature, replay, dedup, amount match)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from scripts.payment_simulator import build_event, sign_event

from app.core.time import utcnow
from app.services.booking_service import payment_reference_for
from tests.factories import auth_header, seed_customer_slot

pytestmark = pytest.mark.api

SECRET = "test-webhook-secret"  # matches conftest env


def _hdr(user, key=None):
    return {**auth_header(user), "Idempotency-Key": key or uuid.uuid4().hex}


async def _make_booking(client, db_session):
    customer, slot = await seed_customer_slot(db_session, capacity=5)
    reservation = (
        await client.post(
            "/api/v1/reservations",
            json={"slot_id": str(slot.id), "quantity": 1},
            headers=_hdr(customer),
        )
    ).json()
    booking = (
        await client.post(
            "/api/v1/bookings",
            json={"reservation_id": reservation["id"]},
            headers=_hdr(customer),
        )
    ).json()
    return customer, slot, booking


def _event_for(booking, *, event_type="payment.succeeded", amount_minor=None, currency=None):
    from app.domain.money import to_minor_units

    amt = (
        amount_minor
        if amount_minor is not None
        else to_minor_units(Decimal(str(booking["total_price"])), booking["currency"])
    )
    return build_event(
        event_id=f"evt_{uuid.uuid4().hex}",
        provider_reference=payment_reference_for(uuid.UUID(booking["id"])),
        amount_minor=amt,
        currency=currency or booking["currency"],
        event_type=event_type,
    )


async def _post_webhook(client, signed):
    return await client.post(
        "/api/v1/webhooks/payments", content=signed.body, headers=signed.headers
    )


async def test_valid_webhook_confirms_booking(client, db_session) -> None:
    customer, _slot, booking = await _make_booking(client, db_session)
    signed = sign_event(_event_for(booking), secret=SECRET)
    resp = await _post_webhook(client, signed)
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"

    got = await client.get(f"/api/v1/bookings/{booking['id']}", headers=auth_header(customer))
    assert got.json()["status"] == "confirmed"


async def test_invalid_signature_rejected(client, db_session) -> None:
    _c, _s, booking = await _make_booking(client, db_session)
    signed = sign_event(_event_for(booking), secret=SECRET, tamper_signature=True)
    resp = await _post_webhook(client, signed)
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "invalid_webhook_signature"


async def test_stale_timestamp_rejected(client, db_session) -> None:
    _c, _s, booking = await _make_booking(client, db_session)
    old_ts = int(utcnow().timestamp()) - 10_000
    signed = sign_event(_event_for(booking), secret=SECRET, timestamp=old_ts)
    resp = await _post_webhook(client, signed)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "webhook_timestamp_out_of_window"


async def test_duplicate_event_deduplicated(client, db_session) -> None:
    _c, _s, booking = await _make_booking(client, db_session)
    signed = sign_event(_event_for(booking), secret=SECRET)
    first = await _post_webhook(client, signed)
    second = await _post_webhook(client, signed)
    assert first.json()["status"] == "processed"
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"


async def test_amount_mismatch_rejected(client, db_session) -> None:
    _c, _s, booking = await _make_booking(client, db_session)
    event = _event_for(booking, amount_minor=1)  # wrong amount
    resp = await _post_webhook(client, sign_event(event, secret=SECRET))
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "payment_amount_mismatch"


async def test_currency_mismatch_rejected(client, db_session) -> None:
    _c, _s, booking = await _make_booking(client, db_session)
    event = _event_for(booking, currency="USD")
    resp = await _post_webhook(client, sign_event(event, secret=SECRET))
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "payment_amount_mismatch"


async def test_unknown_reference_404(client) -> None:
    event = build_event(
        event_id=f"evt_{uuid.uuid4().hex}",
        provider_reference="pi_nonexistent",
        amount_minor=100,
        currency="SGD",
    )
    resp = await _post_webhook(client, sign_event(event, secret=SECRET))
    assert resp.status_code == 404


async def test_payment_failed_releases_inventory(client, db_session) -> None:
    _c, slot, booking = await _make_booking(client, db_session)
    event = _event_for(booking, event_type="payment.failed")
    resp = await _post_webhook(client, sign_event(event, secret=SECRET))
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"
    await db_session.refresh(slot)
    assert slot.confirmed_quantity == 0
