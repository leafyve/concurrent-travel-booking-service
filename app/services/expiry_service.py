"""Reservation-expiry service (used by the expiry worker).

Finds active reservations past their ``expires_at`` in bounded batches, releases
their held inventory **exactly once**, marks them expired, and emits an outbox
event — all in one transaction. ``FOR UPDATE SKIP LOCKED`` lets multiple workers
run safely in parallel without double-processing a reservation.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.domain.enums import ReservationStatus, SlotStatus
from app.observability.metrics import RESERVATIONS_EXPIRED, WORKER_BATCH_DURATION
from app.repositories.experience_repo import ExperienceRepository
from app.repositories.reservation_repo import ReservationRepository
from app.services.events import enqueue_event


class ReservationExpiryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._reservations = ReservationRepository(session)
        self._experiences = ExperienceRepository(session)

    async def run_batch(self, limit: int) -> int:
        """Expire up to ``limit`` reservations; return how many were expired."""
        with WORKER_BATCH_DURATION.labels("reservation_expiry").time():
            now = utcnow()
            reservations = await self._reservations.fetch_expired_for_update(now, limit)
            for reservation in reservations:
                slot = await self._experiences.get_slot_for_update(reservation.slot_id)
                if slot is not None:
                    slot.reserved_quantity -= reservation.quantity
                    slot.version += 1
                    if slot.status == SlotStatus.SOLD_OUT and slot.available_quantity > 0:
                        slot.status = SlotStatus.OPEN
                reservation.status = ReservationStatus.EXPIRED
                enqueue_event(
                    self._session,
                    aggregate_type="reservation",
                    aggregate_id=reservation.id,
                    event_type="reservation.expired",
                    payload={
                        "reservation_id": str(reservation.id),
                        "slot_id": str(reservation.slot_id),
                        "quantity": reservation.quantity,
                    },
                )
            await self._session.commit()

        count = len(reservations)
        if count:
            RESERVATIONS_EXPIRED.inc(count)
        return count
