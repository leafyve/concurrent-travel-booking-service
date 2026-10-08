"""Merchant inventory synchronisation — a safe partner-facing API boundary.

Rules enforced here:

* Only the **owning merchant** may modify a slot (ownership check on the slot's
  experience).
* Capacity can never be reduced below **committed** inventory
  (``reserved + confirmed``) — otherwise existing customers would be oversold.
* Every accepted *or* rejected update is persisted (an auditable partner log),
  and duplicate ``external_update_id``s are idempotent.
"""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import PartnerUpdateStatus, SlotStatus, UserRole
from app.domain.errors import AuthorizationError, NotFoundError
from app.models.partner import PartnerInventoryUpdate
from app.repositories.audit_repo import AuditRepository
from app.repositories.merchant_repo import MerchantRepository
from app.schemas.merchant import InventoryUpdateOut, InventoryUpdateRequest
from app.services.events import enqueue_event


class MerchantInventoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._merchants = MerchantRepository(session)
        self._audit = AuditRepository(session)

    async def apply_update(
        self,
        *,
        owner_user_id: uuid.UUID,
        payload: InventoryUpdateRequest,
    ) -> InventoryUpdateOut:
        merchant = await self._merchants.get_by_owner(owner_user_id)
        if merchant is None:
            raise AuthorizationError("No merchant account for this user.")

        # Idempotent replay of a previously seen external update id.
        existing = await self._merchants.get_update_by_external_id(
            merchant.id, payload.external_update_id
        )
        if existing is not None:
            return InventoryUpdateOut.model_validate(existing)

        locked = await self._merchants.get_slot_with_experience_for_update(payload.slot_id)
        if locked is None:
            raise NotFoundError("Slot not found.")
        slot, experience = locked
        if experience.merchant_id != merchant.id:
            raise AuthorizationError("This slot belongs to another merchant.")

        committed = slot.reserved_quantity + slot.confirmed_quantity
        if payload.requested_capacity < committed:
            status = PartnerUpdateStatus.REJECTED
            validation_result = {
                "accepted": False,
                "reason": "capacity_below_committed",
                "committed_units": committed,
                "requested_capacity": payload.requested_capacity,
                "message": (
                    "Requested capacity is below committed inventory "
                    f"({committed} units reserved/confirmed)."
                ),
            }
        else:
            slot.capacity = payload.requested_capacity
            slot.version += 1
            if slot.available_quantity == 0 and slot.status == SlotStatus.OPEN:
                slot.status = SlotStatus.SOLD_OUT
            elif slot.available_quantity > 0 and slot.status == SlotStatus.SOLD_OUT:
                slot.status = SlotStatus.OPEN
            status = PartnerUpdateStatus.ACCEPTED
            validation_result = {
                "accepted": True,
                "new_capacity": payload.requested_capacity,
                "committed_units": committed,
            }

        update = PartnerInventoryUpdate(
            merchant_id=merchant.id,
            external_update_id=payload.external_update_id,
            slot_id=slot.id,
            requested_capacity=payload.requested_capacity,
            status=status,
            validation_result=validation_result,
        )
        self._merchants.add_update(update)
        self._audit.record(
            action="inventory.update",
            entity_type="experience_slot",
            entity_id=slot.id,
            actor_id=owner_user_id,
            actor_role=UserRole.MERCHANT.value,
            context={
                "external_update_id": payload.external_update_id,
                "status": status.value,
                "requested_capacity": payload.requested_capacity,
            },
        )
        if status == PartnerUpdateStatus.ACCEPTED:
            enqueue_event(
                self._session,
                aggregate_type="experience_slot",
                aggregate_id=slot.id,
                event_type="inventory.updated",
                payload={
                    "slot_id": str(slot.id),
                    "merchant_id": str(merchant.id),
                    "new_capacity": payload.requested_capacity,
                },
            )

        try:
            await self._session.flush()
        except IntegrityError:
            # Concurrent duplicate external_update_id won the race — replay it.
            await self._session.rollback()
            winner = await self._merchants.get_update_by_external_id(
                merchant.id, payload.external_update_id
            )
            if winner is None:  # pragma: no cover
                raise
            return InventoryUpdateOut.model_validate(winner)

        await self._session.commit()
        return InventoryUpdateOut.model_validate(update)
