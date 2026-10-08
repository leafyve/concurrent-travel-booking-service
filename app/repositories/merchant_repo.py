"""Merchant & partner-update persistence."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.experience import Experience, ExperienceSlot
from app.models.merchant import Merchant
from app.models.partner import PartnerInventoryUpdate


class MerchantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_owner(self, owner_user_id: uuid.UUID) -> Merchant | None:
        stmt = select(Merchant).where(Merchant.owner_user_id == owner_user_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, merchant_id: uuid.UUID) -> Merchant | None:
        return await self._session.get(Merchant, merchant_id)

    async def get_slot_with_experience_for_update(
        self, slot_id: uuid.UUID
    ) -> tuple[ExperienceSlot, Experience] | None:
        """Lock a slot and load its owning experience (for ownership checks)."""
        stmt = (
            select(ExperienceSlot, Experience)
            .join(Experience, ExperienceSlot.experience_id == Experience.id)
            .where(ExperienceSlot.id == slot_id)
            .with_for_update(of=ExperienceSlot)
        )
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            return None
        return row[0], row[1]

    def add_update(self, update: PartnerInventoryUpdate) -> None:
        self._session.add(update)

    async def get_update_by_external_id(
        self, merchant_id: uuid.UUID, external_update_id: str
    ) -> PartnerInventoryUpdate | None:
        stmt = select(PartnerInventoryUpdate).where(
            PartnerInventoryUpdate.merchant_id == merchant_id,
            PartnerInventoryUpdate.external_update_id == external_update_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()
