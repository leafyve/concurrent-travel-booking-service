"""End-to-end lifecycle demonstration against a running API.

Exercises the full happy path *and* the safety guarantees, asserting invariants
at each step. Exits non-zero with a clear message if any invariant is violated.

Prerequisites: the API is running and the database has been seeded
(``python -m scripts.seed``). Configure via env:

* ``DEMO_BASE_URL`` (default ``http://localhost:8000``)
* ``WEBHOOK_SIGNING_SECRET`` (must match the server's)

Run: ``python -m scripts.demo``
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from decimal import Decimal

import httpx

from app.domain.money import to_minor_units
from app.services.booking_service import payment_reference_for
from scripts.payment_simulator import sign_event

BASE_URL = os.environ.get("DEMO_BASE_URL", "http://localhost:8000")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SIGNING_SECRET", "local-dev-webhook-secret-abcdef")
CUSTOMER_EMAIL = os.environ.get("DEMO_CUSTOMER", "customer.alice@demo.test")
CUSTOMER_PASSWORD = os.environ.get("DEMO_PASSWORD", "Password123!")


class DemoError(RuntimeError):
    """Raised when a demonstrated invariant does not hold."""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise DemoError(message)


async def _login(client: httpx.AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": CUSTOMER_EMAIL, "password": CUSTOMER_PASSWORD},
    )
    check(resp.status_code == 200, f"login failed: {resp.status_code} {resp.text}")
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _pick_available_slot(client: httpx.AsyncClient) -> tuple[str, int]:
    resp = await client.get("/api/v1/experiences", params={"min_available_capacity": 1})
    check(resp.status_code == 200, f"search failed: {resp.text}")
    for experience in resp.json()["items"]:
        slots = await client.get(f"/api/v1/experiences/{experience['id']}/slots")
        for slot in slots.json():
            if slot["available_capacity"] >= 1 and slot["status"] == "open":
                return slot["id"], slot["available_capacity"]
    raise DemoError("no slot with available capacity found — run scripts.seed first")


async def _availability(client: httpx.AsyncClient, experience_slots_url: str, slot_id: str) -> int:
    resp = await client.get(experience_slots_url)
    for slot in resp.json():
        if slot["id"] == slot_id:
            return int(slot["available_capacity"])
    raise DemoError("slot vanished from availability listing")


async def run() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        print(f"→ Using API at {BASE_URL}")
        auth = await _login(client)
        print(f"✓ Logged in as {CUSTOMER_EMAIL}")

        slot_id, available_before = await _pick_available_slot(client)
        # Find the experience slots URL for availability re-checks.
        exp_resp = await client.get("/api/v1/experiences", params={"min_available_capacity": 1})
        slots_url = None
        for experience in exp_resp.json()["items"]:
            slots = await client.get(f"/api/v1/experiences/{experience['id']}/slots")
            if any(s["id"] == slot_id for s in slots.json()):
                slots_url = f"/api/v1/experiences/{experience['id']}/slots"
                break
        check(slots_url is not None, "could not locate slots url")
        assert slots_url is not None
        print(f"✓ Selected slot {slot_id} (available={available_before})")

        # --- Reservation + idempotent retry ---
        key1 = uuid.uuid4().hex
        body = {"slot_id": slot_id, "quantity": 1}
        r1 = await client.post(
            "/api/v1/reservations", json=body, headers={**auth, "Idempotency-Key": key1}
        )
        check(r1.status_code == 201, f"reservation failed: {r1.text}")
        reservation = r1.json()
        print(
            f"✓ Reservation created: {reservation['id']} total={reservation['total_price']} {reservation['currency']}"
        )

        r2 = await client.post(
            "/api/v1/reservations", json=body, headers={**auth, "Idempotency-Key": key1}
        )
        check(
            r2.json()["id"] == reservation["id"],
            "idempotent retry returned a DIFFERENT reservation!",
        )
        check(r2.headers.get("Idempotent-Replayed") == "true", "retry was not flagged as replayed")
        print("✓ Idempotent retry returned the same reservation (no duplicate)")

        r3 = await client.post(
            "/api/v1/reservations",
            json={"slot_id": slot_id, "quantity": 2},
            headers={**auth, "Idempotency-Key": key1},
        )
        check(
            r3.status_code == 409,
            f"reused key with different body should 409, got {r3.status_code}",
        )
        print("✓ Same key + different payload correctly rejected with 409")

        # --- Booking confirmation ---
        b1 = await client.post(
            "/api/v1/bookings",
            json={"reservation_id": reservation["id"]},
            headers={**auth, "Idempotency-Key": uuid.uuid4().hex},
        )
        check(b1.status_code == 201, f"booking failed: {b1.text}")
        booking = b1.json()
        check(booking["status"] == "pending_payment", f"unexpected status {booking['status']}")
        print(f"✓ Booking confirmed (pending payment): {booking['booking_reference']}")

        # --- Signed payment webhook + replay ---
        provider_ref = payment_reference_for(uuid.UUID(booking["id"]))
        amount_minor = to_minor_units(Decimal(str(booking["total_price"])), booking["currency"])
        event = {
            "event_id": f"evt_{uuid.uuid4().hex}",
            "type": "payment.succeeded",
            "provider_reference": provider_ref,
            "amount_minor": amount_minor,
            "currency": booking["currency"],
        }
        signed = sign_event(event, secret=WEBHOOK_SECRET)
        w1 = await client.post(
            "/api/v1/webhooks/payments", content=signed.body, headers=signed.headers
        )
        check(
            w1.status_code == 200 and w1.json()["status"] == "processed",
            f"webhook failed: {w1.text}",
        )
        print("✓ Payment webhook processed (booking confirmed)")

        w2 = await client.post(
            "/api/v1/webhooks/payments", content=signed.body, headers=signed.headers
        )
        check(
            w2.status_code == 200 and w2.json()["status"] == "duplicate",
            f"replay not deduped: {w2.text}",
        )
        print("✓ Replayed webhook safely deduplicated")

        # --- Confirmed booking lookup ---
        g1 = await client.get(f"/api/v1/bookings/{booking['id']}", headers=auth)
        check(g1.json()["status"] == "confirmed", f"booking not confirmed: {g1.json()['status']}")
        print("✓ Booking is CONFIRMED")

        # --- Cancellation + restore-once ---
        c1 = await client.post(f"/api/v1/bookings/{booking['id']}/cancel", headers=auth)
        check(c1.status_code == 200, f"cancel failed: {c1.text}")
        print(f"✓ Booking cancelled (refundable={c1.json()['refundable']})")

        c2 = await client.post(f"/api/v1/bookings/{booking['id']}/cancel", headers=auth)
        check(c2.status_code == 200, "second cancel should be idempotent")
        print("✓ Duplicate cancellation handled idempotently")

        available_after = await _availability(client, slots_url, slot_id)
        check(
            available_after == available_before,
            f"inventory not restored exactly once: before={available_before} after={available_after}",
        )
        print(f"✓ Inventory restored exactly once (available back to {available_after})")

        print("\nAll lifecycle invariants held. Demo succeeded. ✅")


def main() -> None:
    try:
        asyncio.run(run())
    except DemoError as exc:
        print(f"\n✗ INVARIANT VIOLATED: {exc}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPError as exc:
        print(f"\n✗ HTTP error talking to {BASE_URL}: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
