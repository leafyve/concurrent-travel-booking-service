"""Merchant (partner) inventory-sync schemas."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import Field

from app.domain.enums import PartnerUpdateStatus
from app.schemas.common import ApiModel


class InventoryUpdateRequest(ApiModel):
    external_update_id: str = Field(
        min_length=1,
        max_length=120,
        description="Partner-side idempotency id for this update.",
    )
    slot_id: uuid.UUID
    requested_capacity: int = Field(ge=0, le=100_000)


class InventoryUpdateOut(ApiModel):
    id: uuid.UUID
    slot_id: uuid.UUID
    external_update_id: str
    requested_capacity: int
    status: PartnerUpdateStatus
    validation_result: dict[str, Any]
