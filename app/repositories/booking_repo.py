"""Booking & payment-attempt persistence."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, PaymentAttempt


class BookingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, booking: Booking) -> None:
        self._session.add(booking)

    async def get_by_id(self, booking_id: uuid.UUID) -> Booking | None:
        return await self._session.get(Booking, booking_id)

    async def get_for_update(self, booking_id: uuid.UUID) -> Booking | None:
        stmt = select(Booking).where(Booking.id == booking_id).with_for_update()
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_reference(self, reference: str) -> Booking | None:
        stmt = select(Booking).where(Booking.booking_reference == reference)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_reservation_id(self, reservation_id: uuid.UUID) -> Booking | None:
        stmt = select(Booking).where(Booking.reservation_id == reservation_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, attempt: PaymentAttempt) -> None:
        self._session.add(attempt)

    async def get_by_event_id(self, event_id: str) -> PaymentAttempt | None:
        stmt = select(PaymentAttempt).where(PaymentAttempt.event_id == event_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_pending_for_booking(self, booking_id: uuid.UUID) -> PaymentAttempt | None:
        stmt = (
            select(PaymentAttempt)
            .where(
                PaymentAttempt.booking_id == booking_id,
                PaymentAttempt.event_id.is_(None),
            )
            .order_by(PaymentAttempt.created_at.asc())
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def find_booking_id_by_provider_reference(
        self, provider_reference: str
    ) -> uuid.UUID | None:
        stmt = (
            select(PaymentAttempt.booking_id)
            .where(PaymentAttempt.provider_reference == provider_reference)
            .order_by(PaymentAttempt.created_at.asc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()
