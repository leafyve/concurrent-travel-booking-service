"""Partner (merchant) inventory update audit model."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.domain.enums import PartnerUpdateStatus
from app.models._columns import enum_column


class PartnerInventoryUpdate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "partner_inventory_updates"
    __table_args__ = (
        # Deduplicate a partner's external update id (idempotent sync).
        UniqueConstraint(
            "merchant_id",
            "external_update_id",
            name="uq_partner_update_external_id",
        ),
    )

    merchant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("merchants.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_update_id: Mapped[str] = mapped_column(String(120), nullable=False)
    slot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experience_slots.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PartnerUpdateStatus] = mapped_column(
        enum_column(PartnerUpdateStatus),
        nullable=False,
    )
    validation_result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
