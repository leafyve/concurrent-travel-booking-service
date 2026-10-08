"""Experience search and availability (read side)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import NotFoundError
from app.repositories.experience_repo import (
    ExperienceRepository,
    ExperienceSearchFilters,
)
from app.schemas.common import Page
from app.schemas.experience import (
    ExperienceDetail,
    ExperienceListItem,
    SlotAvailability,
)


class ExperienceService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = ExperienceRepository(session)

    async def search(self, filters: ExperienceSearchFilters) -> Page[ExperienceListItem]:
        experiences, total = await self._repo.search(filters)
        return Page[ExperienceListItem](
            items=[ExperienceListItem.model_validate(e) for e in experiences],
            total=total,
            limit=filters.limit,
            offset=filters.offset,
        )

    async def get_detail(self, experience_id: uuid.UUID) -> ExperienceDetail:
        experience = await self._repo.get_by_id(experience_id)
        if experience is None:
            raise NotFoundError("Experience not found.")
        return ExperienceDetail.model_validate(experience)

    async def list_availability(
        self,
        experience_id: uuid.UUID,
        *,
        starts_from: datetime | None = None,
        starts_to: datetime | None = None,
    ) -> list[SlotAvailability]:
        experience = await self._repo.get_by_id(experience_id)
        if experience is None:
            raise NotFoundError("Experience not found.")
        slots = await self._repo.list_slots(
            experience_id, starts_from=starts_from, starts_to=starts_to
        )
        return [
            SlotAvailability(
                id=slot.id,
                experience_id=slot.experience_id,
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
                currency=experience.currency,
                price=experience.base_price,
                total_capacity=slot.capacity,
                available_capacity=max(slot.available_quantity, 0),
                status=slot.status,
            )
            for slot in slots
        ]
