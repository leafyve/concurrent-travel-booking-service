"""Payment webhook schemas.

The webhook body mirrors a real provider: an ``event_id`` for deduplication, a
``provider_reference`` linking to the payment intent, and an ``amount`` expressed
in integer **minor units** (e.g. cents) plus a currency.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel


class PaymentWebhookEvent(ApiModel):
    event_id: str = Field(min_length=1, max_length=120)
    type: Literal["payment.succeeded", "payment.failed"]
    provider_reference: str = Field(min_length=1, max_length=100)
    amount_minor: int = Field(ge=0, description="Amount in integer minor units.")
    currency: str = Field(min_length=3, max_length=3)


class WebhookAck(ApiModel):
    received: bool = True
    status: str
    detail: str
