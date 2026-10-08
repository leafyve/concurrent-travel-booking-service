"""Experience & slot persistence, including the search read model.

The search query uses a single ``EXISTS`` subquery for the availability filter
so listing experiences never fans out into per-row slot queries (no N+1).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ExperienceStatus, SlotStatus
from app.models.experience import Experience, ExperienceSlot


@dataclass(frozen=True, slots=True)
class ExperienceSearchFilters:
    destination: str | None = None
    category: str | None = None
    starts_from: datetime | None = None
    starts_to: datetime | None = None
    min_available_capacity: int = 0
    limit: int = 20
    offset: int = 0


class ExperienceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _available_slot_exists(self, filters: ExperienceSearchFilters) -> Select[tuple[int]]:
        available = (
            ExperienceSlot.capacity
            - ExperienceSlot.reserved_quantity
            - ExperienceSlot.confirmed_quantity
        )
        conditions = [
            ExperienceSlot.experience_id == Experience.id,
            ExperienceSlot.status == SlotStatus.OPEN,
            available >= filters.min_available_capacity,
        ]
        if filters.starts_from is not None:
            conditions.append(ExperienceSlot.starts_at >= filters.starts_from)
        if filters.starts_to is not None:
            conditions.append(ExperienceSlot.starts_at <= filters.starts_to)
        return select(1).where(and_(*conditions))

    def _base_query(self, filters: ExperienceSearchFilters) -> Select[tuple[Experience]]:
        conditions = [Experience.status == ExperienceStatus.PUBLISHED]
        if filters.destination:
            conditions.append(func.lower(Experience.destination) == filters.destination.lower())
        if filters.category:
            conditions.append(func.lower(Experience.category) == filters.category.lower())

        needs_slot_filter = (
            filters.min_available_capacity > 0
            or filters.starts_from is not None
            or filters.starts_to is not None
        )
        stmt = select(Experience).where(and_(*conditions))
        if needs_slot_filter:
            stmt = stmt.where(exists(self._available_slot_exists(filters)))
        return stmt

    async def search(self, filters: ExperienceSearchFilters) -> tuple[list[Experience], int]:
        base = self._base_query(filters)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        # Deterministic ordering: title, then id as a stable tiebreaker.
        page_stmt = (
            base.order_by(Experience.title.asc(), Experience.id.asc())
            .limit(filters.limit)
            .offset(filters.offset)
        )
        rows = (await self._session.execute(page_stmt)).scalars().all()
        return list(rows), total

    async def get_by_id(self, experience_id: uuid.UUID) -> Experience | None:
        return await self._session.get(Experience, experience_id)

    async def list_slots(
        self,
        experience_id: uuid.UUID,
        *,
        starts_from: datetime | None = None,
        starts_to: datetime | None = None,
    ) -> list[ExperienceSlot]:
        conditions = [ExperienceSlot.experience_id == experience_id]
        if starts_from is not None:
            conditions.append(ExperienceSlot.starts_at >= starts_from)
        if starts_to is not None:
            conditions.append(ExperienceSlot.starts_at <= starts_to)
        stmt = (
            select(ExperienceSlot)
            .where(and_(*conditions))
            .order_by(ExperienceSlot.starts_at.asc(), ExperienceSlot.id.asc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_slot(self, slot_id: uuid.UUID) -> ExperienceSlot | None:
        return await self._session.get(ExperienceSlot, slot_id)

    async def get_slot_for_update(self, slot_id: uuid.UUID) -> ExperienceSlot | None:
        """Fetch a slot row with ``SELECT ... FOR UPDATE`` (row-level lock).

        This is the core of overselling prevention: concurrent reservations for
        the same slot serialize on this lock, so capacity checks are exclusive.
        """
        stmt = select(ExperienceSlot).where(ExperienceSlot.id == slot_id).with_for_update()
        return (await self._session.execute(stmt)).scalar_one_or_none()
