"""SQLAlchemy ORM models.

Importing this package registers every model on ``Base.metadata`` so Alembic
autogenerate and ``create_all`` see the full schema. Import order is arranged so
foreign-key targets are defined before their referrers.
"""

from __future__ import annotations

from app.models.audit import AuditEvent
from app.models.booking import Booking, PaymentAttempt
from app.models.experience import Experience, ExperienceSlot
from app.models.idempotency import IdempotencyRecord
from app.models.merchant import Merchant
from app.models.outbox import OutboxEvent
from app.models.partner import PartnerInventoryUpdate
from app.models.reservation import Reservation
from app.models.user import User

__all__ = [
    "AuditEvent",
    "Booking",
    "Experience",
    "ExperienceSlot",
    "IdempotencyRecord",
    "Merchant",
    "OutboxEvent",
    "PartnerInventoryUpdate",
    "PaymentAttempt",
    "Reservation",
    "User",
]
