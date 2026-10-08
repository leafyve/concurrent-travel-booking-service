"""Booking schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from app.domain.enums import BookingStatus
from app.schemas.common import ApiModel


class BookingCreate(ApiModel):
    reservation_id: uuid.UUID


class BookingOut(ApiModel):
    id: uuid.UUID
    booking_reference: str
    reservation_id: uuid.UUID
    customer_id: uuid.UUID
    slot_id: uuid.UUID
    quantity: int
    total_price: Decimal
    currency: str
    status: BookingStatus
    created_at: datetime
    cancelled_at: datetime | None = None


class CancellationOut(ApiModel):
    booking: BookingOut
    refundable: bool
    refund_amount: Decimal
    reason: str
