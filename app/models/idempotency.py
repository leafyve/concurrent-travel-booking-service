"""Idempotency record model.

Stores the outcome of a successfully-processed mutating request so that a retry
with the same key returns the identical response. The request fingerprint lets
us detect a *different* payload reusing the same key (→ 409 conflict).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class IdempotencyRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        # A key is scoped to (actor, operation): the same key used against a
        # different endpoint or by a different actor is independent.
        UniqueConstraint(
            "idempotency_key",
            "endpoint",
            "actor_id",
            name="uq_idempotency_scope",
        ),
    )

    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    endpoint: Mapped[str] = mapped_column(String(120), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
