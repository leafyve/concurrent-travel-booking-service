"""Payment webhook processing (simulation only — no real provider).

Security & correctness layers, in order:

1. **HMAC signature** over ``"{timestamp}.{raw_body}"`` (constant-time compare).
2. **Replay window** on the timestamp.
3. **Event dedup** via the UNIQUE ``payment_attempts.event_id`` — a replayed
   event is a safe no-op even under concurrency.
4. **Amount + currency match** against the booking total (integer minor units).

The signing secret is never logged.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time import utcnow
from app.domain.enums import BookingStatus, PaymentStatus, SlotStatus
from app.domain.errors import (
    NotFoundError,
    PaymentAmountMismatchError,
    ValidationFailedError,
    WebhookReplayError,
    WebhookSignatureError,
)
from app.domain.money import to_minor_units
from app.domain.signatures import is_within_replay_window, verify_signature
from app.models.booking import Booking, PaymentAttempt
from app.observability.metrics import BOOKINGS_CONFIRMED, WEBHOOK_REJECTIONS
from app.repositories.booking_repo import BookingRepository, PaymentRepository
from app.repositories.experience_repo import ExperienceRepository
from app.schemas.webhook import PaymentWebhookEvent, WebhookAck
from app.services.events import enqueue_event


class PaymentWebhookService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._bookings = BookingRepository(session)
        self._payments = PaymentRepository(session)
        self._experiences = ExperienceRepository(session)

    async def process(
        self, *, raw_body: bytes, timestamp: int | None, signature: str | None
    ) -> tuple[int, WebhookAck]:
        settings = get_settings()

        # 1) Signature + timestamp presence.
        if not signature or timestamp is None:
            WEBHOOK_REJECTIONS.labels("missing_signature").inc()
            raise WebhookSignatureError("Missing signature or timestamp header.")

        # 2) Replay window.
        if not is_within_replay_window(
            timestamp, int(utcnow().timestamp()), settings.webhook_replay_window_seconds
        ):
            WEBHOOK_REJECTIONS.labels("replay_window").inc()
            raise WebhookReplayError("Webhook timestamp outside the accepted window.")

        # 3) Signature verification (constant-time).
        if not verify_signature(settings.webhook_signing_secret, timestamp, raw_body, signature):
            WEBHOOK_REJECTIONS.labels("invalid_signature").inc()
            raise WebhookSignatureError("Invalid webhook signature.")

        # 4) Parse + validate the payload.
        try:
            event = PaymentWebhookEvent.model_validate_json(raw_body)
        except ValueError as exc:
            WEBHOOK_REJECTIONS.labels("malformed_payload").inc()
            raise ValidationFailedError("Malformed webhook payload.") from exc

        # 5) Fast-path dedup (also enforced by the DB unique constraint below).
        if await self._payments.get_by_event_id(event.event_id) is not None:
            return 200, WebhookAck(status="duplicate", detail="Event already processed.")

        booking_id = await self._payments.find_booking_id_by_provider_reference(
            event.provider_reference
        )
        if booking_id is None:
            WEBHOOK_REJECTIONS.labels("unknown_reference").inc()
            raise NotFoundError("No booking matches this payment reference.")

        booking = await self._bookings.get_for_update(booking_id)
        if booking is None:  # pragma: no cover
            raise NotFoundError("Booking not found.")

        # 6) Amount + currency must match the booking total.
        expected_minor = to_minor_units(booking.total_price, booking.currency)
        if (
            event.currency.upper() != booking.currency.upper()
            or event.amount_minor != expected_minor
        ):
            WEBHOOK_REJECTIONS.labels("amount_mismatch").inc()
            raise PaymentAmountMismatchError(
                "Webhook amount or currency does not match the booking.",
                extra={"expected_minor": expected_minor, "currency": booking.currency},
            )

        succeeded = event.type == "payment.succeeded"
        attempt = PaymentAttempt(
            booking_id=booking.id,
            provider_reference=event.provider_reference,
            amount=booking.total_price,
            currency=booking.currency,
            status=PaymentStatus.SUCCEEDED if succeeded else PaymentStatus.FAILED,
            event_id=event.event_id,
        )
        self._payments.add(attempt)

        try:
            if succeeded:
                await self._apply_success(booking)
                ack = WebhookAck(status="processed", detail="Payment confirmed.")
            else:
                await self._apply_failure(booking)
                ack = WebhookAck(status="failed", detail="Payment marked as failed.")
            await self._session.commit()
        except IntegrityError:
            # A concurrent duplicate won the unique(event_id) race — safe no-op.
            await self._session.rollback()
            return 200, WebhookAck(status="duplicate", detail="Event already processed.")

        if succeeded:
            BOOKINGS_CONFIRMED.inc()
        return 200, ack

    async def _apply_success(self, booking: Booking) -> None:
        if booking.status == BookingStatus.PENDING_PAYMENT:
            booking.status = BookingStatus.CONFIRMED
            enqueue_event(
                self._session,
                aggregate_type="booking",
                aggregate_id=booking.id,
                event_type="booking.confirmed",
                payload={
                    "booking_id": str(booking.id),
                    "booking_reference": booking.booking_reference,
                },
            )

    async def _apply_failure(self, booking: Booking) -> None:
        if booking.status != BookingStatus.PENDING_PAYMENT:
            return
        booking.status = BookingStatus.PAYMENT_FAILED
        # Release the held inventory since payment did not complete.
        slot = await self._experiences.get_slot_for_update(booking.slot_id)
        if slot is not None:
            slot.confirmed_quantity -= booking.quantity
            slot.version += 1
            if slot.status == SlotStatus.SOLD_OUT and slot.available_quantity > 0:
                slot.status = SlotStatus.OPEN
        enqueue_event(
            self._session,
            aggregate_type="booking",
            aggregate_id=booking.id,
            event_type="booking.payment_failed",
            payload={"booking_id": str(booking.id)},
        )
