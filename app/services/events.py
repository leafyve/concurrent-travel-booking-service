"""Outbox event writing.

A tiny helper so services enqueue domain events consistently. The event row is
added to the *current* session and therefore commits atomically with the
business change (transactional outbox pattern).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.models.outbox import OutboxEvent


def enqueue_event(
    session: AsyncSession,
    *,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
) -> OutboxEvent:
    """Add an outbox event to the session (committed with the caller's tx)."""
    event = OutboxEvent(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
        created_at=utcnow(),
    )
    session.add(event)
    return event
