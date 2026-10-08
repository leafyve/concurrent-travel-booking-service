"""Reservation persistence, including the expiry worker's locked batch scan."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ReservationStatus
from app.models.reservation import Reservation


class ReservationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, reservation: Reservation) -> None:
        self._session.add(reservation)

    async def get_by_id(self, reservation_id: uuid.UUID) -> Reservation | None:
        return await self._session.get(Reservation, reservation_id)

    async def get_for_update(self, reservation_id: uuid.UUID) -> Reservation | None:
        """Lock a single reservation row for a confirm/cancel transition."""
        stmt = select(Reservation).where(Reservation.id == reservation_id).with_for_update()
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def fetch_expired_for_update(self, now: datetime, limit: int) -> list[Reservation]:
        """Claim a batch of expired, still-active reservations.

        ``FOR UPDATE SKIP LOCKED`` lets multiple expiry workers run concurrently
        without blocking each other or double-processing a reservation.
        """
        stmt = (
            select(Reservation)
            .where(
                Reservation.status == ReservationStatus.ACTIVE,
                Reservation.expires_at <= now,
            )
            .order_by(Reservation.expires_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self._session.execute(stmt)).scalars().all())
