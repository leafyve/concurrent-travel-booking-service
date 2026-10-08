"""Merchant (partner) routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies.auth import MerchantDep
from app.api.dependencies.db import SessionDep
from app.schemas.merchant import InventoryUpdateOut, InventoryUpdateRequest
from app.services.merchant_service import MerchantInventoryService

router = APIRouter(prefix="/merchant", tags=["merchant"])


@router.post(
    "/inventory-updates",
    response_model=InventoryUpdateOut,
    summary="Submit a merchant inventory (capacity) update",
)
async def submit_inventory_update(
    payload: InventoryUpdateRequest,
    actor: MerchantDep,
    session: SessionDep,
) -> InventoryUpdateOut:
    return await MerchantInventoryService(session).apply_update(
        owner_user_id=actor.id, payload=payload
    )
