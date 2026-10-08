"""Payment webhook route.

The HMAC signature is computed over the **raw request body**, so we read the
body bytes directly rather than a parsed model. Signature and timestamp arrive
as headers, mirroring real payment providers.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.api.dependencies.db import SessionDep
from app.schemas.webhook import PaymentWebhookEvent, WebhookAck
from app.services.payment_service import PaymentWebhookService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

SIGNATURE_HEADER = "X-Webhook-Signature"
TIMESTAMP_HEADER = "X-Webhook-Timestamp"

# Document the expected body schema without letting FastAPI parse/validate it —
# the signature must be verified against the *raw* bytes first.
_WEBHOOK_OPENAPI_BODY = {
    "requestBody": {
        "content": {
            "application/json": {
                "schema": PaymentWebhookEvent.model_json_schema(),
            }
        },
        "required": True,
    }
}


@router.post(
    "/payments",
    response_model=WebhookAck,
    summary="Receive a signed payment webhook (HMAC + replay protection)",
    openapi_extra=_WEBHOOK_OPENAPI_BODY,
)
async def payment_webhook(
    request: Request,
    session: SessionDep,
    x_webhook_signature: Annotated[str | None, Header(alias=SIGNATURE_HEADER)] = None,
    x_webhook_timestamp: Annotated[int | None, Header(alias=TIMESTAMP_HEADER)] = None,
) -> JSONResponse:
    raw_body = await request.body()
    status_code, ack = await PaymentWebhookService(session).process(
        raw_body=raw_body,
        timestamp=x_webhook_timestamp,
        signature=x_webhook_signature,
    )
    return JSONResponse(status_code=status_code, content=ack.model_dump())
