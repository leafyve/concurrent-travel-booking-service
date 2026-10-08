"""HMAC signature helpers for the payment webhook.

Mirrors how real providers (e.g. Stripe) sign webhooks: the signed content is
``"{timestamp}.{raw_body}"`` and the signature is a hex HMAC-SHA256 digest. We
also enforce a replay window on the timestamp so a captured-and-replayed request
cannot be accepted indefinitely.

**The signing secret is never logged.** Comparison is constant-time.
"""

from __future__ import annotations

import hashlib
import hmac

_SIGNED_TEMPLATE = "{timestamp}.{body}"


def compute_signature(secret: str, timestamp: int, body: bytes) -> str:
    """Return the hex HMAC-SHA256 signature for ``timestamp`` + ``body``."""
    signed_payload = _SIGNED_TEMPLATE.format(
        timestamp=timestamp,
        body=body.decode("utf-8"),
    ).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()


def verify_signature(secret: str, timestamp: int, body: bytes, provided: str) -> bool:
    """Constant-time verification of a provided signature."""
    expected = compute_signature(secret, timestamp, body)
    return hmac.compare_digest(expected, provided)


def is_within_replay_window(
    timestamp: int,
    now_epoch: int,
    window_seconds: int,
) -> bool:
    """Return True if ``timestamp`` is within ``window_seconds`` of ``now``.

    Rejects both stale timestamps (replay) and timestamps too far in the future
    (clock skew / forgery).
    """
    delta = abs(now_epoch - timestamp)
    return delta <= window_seconds
