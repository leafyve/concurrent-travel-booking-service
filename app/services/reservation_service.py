"""Reservation service — concurrency-safe inventory holds.

Overselling is prevented by locking the slot row (``SELECT ... FOR UPDATE``)
before checking and mutating capacity, all inside one transaction. Concurrent
reservations for the same slot therefore serialize on the lock, and the database
CHECK constraint ``reserved + confirmed <= capacity`` is a second, independent
guarantee that an impossible state can never be persisted.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time import in_minutes, utcnow
from app.domain.enums import ReservationStatus, SlotStatus
from app.domain.errors import InventoryConflictError, NotFoundError
from app.domain.money import compute_total
from app.models.reservation import Reservation
from app.observability.metrics import INVENTORY_CONFLICTS, RESERVATIONS_CREATED
from app.repositories.experience_repo import ExperienceRepository
from app.repositories.reservation_repo import ReservationRepository
from app.schemas.reservation import ReservationCreate, ReservationOut
from app.services.events import enqueue_event
from app.services.idempotency import IdempotencyService, IdempotentResult

ENDPOINT = "POST /api/v1/reservations"


class ReservationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._experiences = ExperienceRepository(session)
        self._reservations = ReservationRepository(session)
        self._idempotency = IdempotencyService(session)

    async def create(
        self,
        *,
        customer_id: uuid.UUID,
        payload: ReservationCreate,
        idempotency_key: str,
    ) -> IdempotentResult:
        async def operation() -> tuple[int, dict]:
            return await self._reserve(customer_id, payload)

        return await self._idempotency.execute(
            key=idempotency_key,
            endpoint=ENDPOINT,
            actor_id=customer_id,
            request_payload=payload.model_dump(mode="json"),
            operation=operation,
        )

    async def _reserve(
        self, customer_id: uuid.UUID, payload: ReservationCreate
    ) -> tuple[int, dict]:
        # Row-level lock: the linchpin of overselling prevention.
        slot = await self._experiences.get_slot_for_update(payload.slot_id)
        if slot is None:
            raise NotFoundError("Slot not found.")
        if slot.status == SlotStatus.CLOSED:
            raise InventoryConflictError("Slot is closed for booking.")
        if slot.starts_at <= utcnow():
            raise InventoryConflictError("Slot has already started.")

        available = slot.capacity - slot.reserved_quantity - slot.confirmed_quantity
        if available < payload.quantity:
            INVENTORY_CONFLICTS.inc()
            raise InventoryConflictError(
                f"Only {max(available, 0)} unit(s) available for this slot.",
                extra={"available": max(available, 0), "requested": payload.quantity},
            )

        experience = await self._experiences.get_by_id(slot.experience_id)
        if experience is None:  # pragma: no cover - FK guarantees presence
            raise NotFoundError("Experience not found.")

        unit_price = experience.base_price
        currency = experience.currency
        total_price = compute_total(unit_price, payload.quantity, currency)

        slot.reserved_quantity += payload.quantity
        slot.version += 1
        if slot.available_quantity == 0:
            slot.status = SlotStatus.SOLD_OUT

        reservation = Reservation(
            customer_id=customer_id,
            slot_id=slot.id,
            quantity=payload.quantity,
            unit_price=unit_price,
            total_price=total_price,
            currency=currency,
            status=ReservationStatus.ACTIVE,
            expires_at=in_minutes(get_settings().reservation_ttl_minutes),
        )
        self._reservations.add(reservation)
        await self._session.flush()  # assign id / timestamps

        enqueue_event(
            self._session,
            aggregate_type="reservation",
            aggregate_id=reservation.id,
            event_type="reservation.created",
            payload={
                "reservation_id": str(reservation.id),
                "slot_id": str(slot.id),
                "customer_id": str(customer_id),
                "quantity": payload.quantity,
                "total_price": str(total_price),
                "currency": currency,
                "expires_at": reservation.expires_at.isoformat(),
            },
        )
        RESERVATIONS_CREATED.inc()

        body = ReservationOut.model_validate(reservation).model_dump(mode="json")
        return 201, body
