"""Booking service — confirmation and cancellation.

Confirmation atomically converts a reservation's *reserved* units into
*confirmed* units and creates exactly one booking (enforced by the UNIQUE
``reservation_id``). Cancellation restores confirmed inventory **exactly once**
by transitioning the booking under a row lock before touching the slot.
"""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.domain.enums import BookingStatus, PaymentStatus, ReservationStatus, SlotStatus, UserRole
from app.domain.errors import (
    AuthorizationError,
    ConflictError,
    DuplicateBookingError,
    NotFoundError,
    ReservationExpiredError,
    ReservationNotActiveError,
)
from app.domain.policies import evaluate_cancellation
from app.domain.references import generate_booking_reference
from app.models.booking import Booking, PaymentAttempt
from app.observability.metrics import BOOKINGS_CANCELLED
from app.repositories.audit_repo import AuditRepository
from app.repositories.booking_repo import BookingRepository, PaymentRepository
from app.repositories.experience_repo import ExperienceRepository
from app.repositories.reservation_repo import ReservationRepository
from app.schemas.booking import BookingCreate, BookingOut, CancellationOut
from app.services.events import enqueue_event
from app.services.idempotency import IdempotencyService, IdempotentResult

CONFIRM_ENDPOINT = "POST /api/v1/bookings"
_MAX_REFERENCE_ATTEMPTS = 5


def payment_reference_for(booking_id: uuid.UUID) -> str:
    """Deterministic simulated payment-intent reference for a booking."""
    return f"pi_{booking_id.hex}"


class BookingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._reservations = ReservationRepository(session)
        self._experiences = ExperienceRepository(session)
        self._bookings = BookingRepository(session)
        self._payments = PaymentRepository(session)
        self._audit = AuditRepository(session)
        self._idempotency = IdempotencyService(session)

    # --- Confirmation -----------------------------------------------------
    async def confirm(
        self,
        *,
        customer_id: uuid.UUID,
        payload: BookingCreate,
        idempotency_key: str,
    ) -> IdempotentResult:
        async def operation() -> tuple[int, dict]:
            return await self._confirm(customer_id, payload)

        return await self._idempotency.execute(
            key=idempotency_key,
            endpoint=CONFIRM_ENDPOINT,
            actor_id=customer_id,
            request_payload=payload.model_dump(mode="json"),
            operation=operation,
        )

    async def _confirm(self, customer_id: uuid.UUID, payload: BookingCreate) -> tuple[int, dict]:
        # Lock the reservation for the confirm transition. If the expiry worker
        # holds it, we block until it commits and then observe EXPIRED.
        reservation = await self._reservations.get_for_update(payload.reservation_id)
        if reservation is None:
            raise NotFoundError("Reservation not found.")
        if reservation.customer_id != customer_id:
            raise AuthorizationError("You do not own this reservation.")

        if reservation.status == ReservationStatus.CONVERTED:
            # Already booked (possibly via a different idempotency key).
            raise DuplicateBookingError("This reservation has already been converted to a booking.")
        if reservation.status == ReservationStatus.EXPIRED:
            raise ReservationExpiredError("This reservation has expired.")
        if reservation.status != ReservationStatus.ACTIVE:
            raise ReservationNotActiveError(
                f"Reservation is {reservation.status.value}, not active."
            )
        if reservation.expires_at <= utcnow():
            # Expired but not yet swept; the worker will release inventory.
            raise ReservationExpiredError("This reservation has expired.")

        slot = await self._experiences.get_slot_for_update(reservation.slot_id)
        if slot is None:  # pragma: no cover - FK guarantees presence
            raise NotFoundError("Slot not found.")

        # Move reserved -> confirmed atomically.
        slot.reserved_quantity -= reservation.quantity
        slot.confirmed_quantity += reservation.quantity
        slot.version += 1
        reservation.status = ReservationStatus.CONVERTED

        booking = await self._insert_booking_with_reference(
            reservation_id=reservation.id,
            customer_id=customer_id,
            slot_id=slot.id,
            quantity=reservation.quantity,
            total_price=reservation.total_price,
            currency=reservation.currency,
        )

        # Pending simulated payment attempt (event_id NULL until a webhook lands).
        self._payments.add(
            PaymentAttempt(
                booking_id=booking.id,
                provider_reference=payment_reference_for(booking.id),
                amount=booking.total_price,
                currency=booking.currency,
                status=PaymentStatus.PENDING,
            )
        )

        enqueue_event(
            self._session,
            aggregate_type="booking",
            aggregate_id=booking.id,
            event_type="booking.created",
            payload={
                "booking_id": str(booking.id),
                "booking_reference": booking.booking_reference,
                "reservation_id": str(reservation.id),
                "slot_id": str(slot.id),
                "quantity": booking.quantity,
                "total_price": str(booking.total_price),
                "currency": booking.currency,
                "payment_reference": payment_reference_for(booking.id),
            },
        )

        body = BookingOut.model_validate(booking).model_dump(mode="json")
        return 201, body

    async def _insert_booking_with_reference(
        self,
        *,
        reservation_id: uuid.UUID,
        customer_id: uuid.UUID,
        slot_id: uuid.UUID,
        quantity: int,
        total_price: object,
        currency: str,
    ) -> Booking:
        """Insert a booking, retrying only on a reference collision.

        The reservation is already locked, so a ``reservation_id`` unique
        violation cannot occur concurrently; any IntegrityError here is a
        (vanishingly rare) booking-reference collision, which we retry.
        """
        last_error: IntegrityError | None = None
        for _ in range(_MAX_REFERENCE_ATTEMPTS):
            booking = Booking(
                booking_reference=generate_booking_reference(),
                reservation_id=reservation_id,
                customer_id=customer_id,
                slot_id=slot_id,
                quantity=quantity,
                total_price=total_price,
                currency=currency,
                status=BookingStatus.PENDING_PAYMENT,
            )
            try:
                async with self._session.begin_nested():
                    self._bookings.add(booking)
                    await self._session.flush()
                return booking
            except IntegrityError as exc:  # savepoint rolled back
                last_error = exc
        raise ConflictError(  # pragma: no cover - astronomically unlikely
            "Could not allocate a unique booking reference."
        ) from last_error

    # --- Cancellation -----------------------------------------------------
    async def cancel(
        self,
        *,
        booking_id: uuid.UUID,
        actor_id: uuid.UUID,
        actor_role: UserRole,
    ) -> CancellationOut:
        booking = await self._bookings.get_for_update(booking_id)
        if booking is None:
            raise NotFoundError("Booking not found.")
        if actor_role != UserRole.ADMIN and booking.customer_id != actor_id:
            raise AuthorizationError("You do not own this booking.")

        # Idempotent: a booking already cancelled returns the same shape and does
        # NOT restore inventory a second time.
        if booking.status == BookingStatus.CANCELLED:
            out = BookingOut.model_validate(booking)
            return CancellationOut(
                booking=out,
                refundable=False,
                refund_amount=booking.total_price * 0,
                reason="Booking was already cancelled.",
            )

        holds_inventory = booking.status in (
            BookingStatus.PENDING_PAYMENT,
            BookingStatus.CONFIRMED,
        )

        slot = await self._experiences.get_slot_for_update(booking.slot_id)
        if slot is None:  # pragma: no cover
            raise NotFoundError("Slot not found.")
        experience = await self._experiences.get_by_id(slot.experience_id)
        if experience is None:  # pragma: no cover
            raise NotFoundError("Experience not found.")

        if holds_inventory:
            slot.confirmed_quantity -= booking.quantity
            slot.version += 1
            if slot.status == SlotStatus.SOLD_OUT and slot.available_quantity > 0:
                slot.status = SlotStatus.OPEN

        amount_paid = (
            booking.total_price
            if booking.status == BookingStatus.CONFIRMED
            else booking.total_price * 0
        )
        outcome = evaluate_cancellation(
            policy=experience.cancellation_policy,
            now=utcnow(),
            slot_starts_at=slot.starts_at,
            amount_paid=amount_paid,
            currency=booking.currency,
        )

        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = utcnow()

        self._audit.record(
            action="booking.cancelled",
            entity_type="booking",
            entity_id=booking.id,
            actor_id=actor_id,
            actor_role=actor_role.value,
            context={
                "refundable": outcome.refundable,
                "refund_amount": str(outcome.refund_amount),
                "policy": experience.cancellation_policy.value,
                "inventory_restored": holds_inventory,
            },
        )
        enqueue_event(
            self._session,
            aggregate_type="booking",
            aggregate_id=booking.id,
            event_type="booking.cancelled",
            payload={
                "booking_id": str(booking.id),
                "slot_id": str(slot.id),
                "quantity": booking.quantity,
                "refundable": outcome.refundable,
                "refund_amount": str(outcome.refund_amount),
            },
        )
        await self._session.commit()
        BOOKINGS_CANCELLED.inc()

        out = BookingOut.model_validate(booking)
        return CancellationOut(
            booking=out,
            refundable=outcome.refundable,
            refund_amount=outcome.refund_amount,
            reason=outcome.reason,
        )

    # --- Read -------------------------------------------------------------
    async def get_booking(
        self, *, booking_id: uuid.UUID, actor_id: uuid.UUID, actor_role: UserRole
    ) -> BookingOut:
        booking = await self._bookings.get_by_id(booking_id)
        if booking is None:
            raise NotFoundError("Booking not found.")
        if actor_role != UserRole.ADMIN and booking.customer_id != actor_id:
            raise AuthorizationError("You do not own this booking.")
        return BookingOut.model_validate(booking)
