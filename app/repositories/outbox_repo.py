"""Outbox event persistence, including the worker's locked batch scan."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import OutboxStatus
from app.models.outbox import OutboxEvent


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, event: OutboxEvent) -> None:
        self._session.add(event)

    async def fetch_pending_for_update(self, limit: int) -> list[OutboxEvent]:
        """Claim a batch of pending events with ``FOR UPDATE SKIP LOCKED``.

        Two outbox workers can run at once without processing the same event
        twice: each claims a disjoint set of rows for the duration of its
        transaction.
        """
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.PENDING)
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self._session.execute(stmt)).scalars().all())
