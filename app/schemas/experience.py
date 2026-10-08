"""Experience & slot schemas (customer-facing, read side)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.domain.enums import (
    CancellationPolicy,
    ExperienceStatus,
    SlotStatus,
)
from app.schemas.common import ApiModel


class ExperienceListItem(ApiModel):
    id: uuid.UUID
    title: str
    slug: str
    destination: str
    category: str
    currency: str
    base_price: Decimal
    cancellation_policy: CancellationPolicy
    status: ExperienceStatus


class ExperienceDetail(ExperienceListItem):
    description: str
    merchant_id: uuid.UUID


class SlotAvailability(ApiModel):
    """Public availability view — deliberately hides reservation internals."""

    id: uuid.UUID
    experience_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    currency: str
    price: Decimal
    total_capacity: int = Field(ge=0)
    available_capacity: int = Field(ge=0)
    status: SlotStatus
