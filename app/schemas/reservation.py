"""Reservation schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.domain.enums import ReservationStatus
from app.schemas.common import ApiModel


class ReservationCreate(ApiModel):
    slot_id: uuid.UUID
    quantity: int = Field(ge=1, le=50, description="Units to hold (1-50).")


class ReservationOut(ApiModel):
    id: uuid.UUID
    slot_id: uuid.UUID
    customer_id: uuid.UUID
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    currency: str
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime
