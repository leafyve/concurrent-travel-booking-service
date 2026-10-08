"""Payment webhook simulator utilities.

Builds correctly-signed (or deliberately invalid) payment webhook requests so the
demo script and the test suite can exercise the webhook endpoint the same way a
real provider would. **Simulation only** — there is no real payment provider.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.core.time import utcnow
from app.domain.signatures import compute_signature

SIGNATURE_HEADER = "X-Webhook-Signature"
TIMESTAMP_HEADER = "X-Webhook-Timestamp"


@dataclass(frozen=True, slots=True)
class SignedWebhook:
    body: bytes
    headers: dict[str, str]


def build_event(
    *,
    event_id: str,
    provider_reference: str,
    amount_minor: int,
    currency: str,
    event_type: str = "payment.succeeded",
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "type": event_type,
        "provider_reference": provider_reference,
        "amount_minor": amount_minor,
        "currency": currency,
    }


def sign_event(
    event: dict[str, object],
    *,
    secret: str,
    timestamp: int | None = None,
    tamper_signature: bool = False,
) -> SignedWebhook:
    """Serialise and sign an event, optionally corrupting the signature."""
    body = json.dumps(event, separators=(",", ":")).encode("utf-8")
    ts = timestamp if timestamp is not None else int(utcnow().timestamp())
    signature = compute_signature(secret, ts, body)
    if tamper_signature:
        signature = "0" * len(signature)
    return SignedWebhook(
        body=body,
        headers={
            SIGNATURE_HEADER: signature,
            TIMESTAMP_HEADER: str(ts),
            "Content-Type": "application/json",
        },
    )
