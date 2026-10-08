"""Audit event persistence."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.models.audit import AuditEvent


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def record(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        actor_role: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            actor_role=actor_role,
            context=context or {},
            created_at=utcnow(),
        )
        self._session.add(event)
        return event
