"""Idempotency record persistence."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency import IdempotencyRecord


class IdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, *, key: str, endpoint: str, actor_id: uuid.UUID
    ) -> IdempotencyRecord | None:
        stmt = select(IdempotencyRecord).where(
            IdempotencyRecord.idempotency_key == key,
            IdempotencyRecord.endpoint == endpoint,
            IdempotencyRecord.actor_id == actor_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    def add(self, record: IdempotencyRecord) -> None:
        self._session.add(record)
