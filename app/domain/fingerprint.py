"""Deterministic request fingerprinting for idempotency.

An idempotency key is only safe if we can detect when the *same* key is reused
with a *different* request body. We compute a canonical fingerprint of the
request payload (stable key ordering, compact separators) and compare SHA-256
digests. Identical payload → replay the stored response; different payload →
409 conflict.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(payload: Any) -> str:
    """Serialise ``payload`` to canonical JSON (sorted keys, compact)."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )


def request_fingerprint(payload: Any) -> str:
    """Return a stable SHA-256 hex digest of a request payload."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
