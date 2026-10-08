"""Experience and ExperienceSlot models — the inventory core.

``ExperienceSlot`` is where inventory correctness lives. The two most important
CHECK constraints are enforced by PostgreSQL itself, so no application bug (or
race) can persist an impossible state:

* quantities can never be negative, and
* ``reserved_quantity + confirmed_quantity`` can never exceed ``capacity``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.domain.enums import CancellationPolicy, ExperienceStatus, SlotStatus
from app.models._columns import enum_column


class Experience(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "experiences"
    __table_args__ = (Index("ix_experiences_search", "destination", "category", "status"),)

    merchant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("merchants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False)
    destination: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[ExperienceStatus] = mapped_column(
        enum_column(ExperienceStatus),
        default=ExperienceStatus.PUBLISHED,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cancellation_policy: Mapped[CancellationPolicy] = mapped_column(
        enum_column(CancellationPolicy),
        nullable=False,
    )

    slots: Mapped[list[ExperienceSlot]] = relationship(
        back_populates="experience",
        cascade="all, delete-orphan",
    )


class ExperienceSlot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "experience_slots"
    __table_args__ = (
        CheckConstraint("capacity >= 0", name="capacity_non_negative"),
        CheckConstraint("reserved_quantity >= 0", name="reserved_non_negative"),
        CheckConstraint("confirmed_quantity >= 0", name="confirmed_non_negative"),
        CheckConstraint(
            "reserved_quantity + confirmed_quantity <= capacity",
            name="committed_within_capacity",
        ),
        Index("ix_experience_slots_experience_start", "experience_id", "starts_at"),
    )

    experience_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experiences.id", ondelete="CASCADE"),
        nullable=False,
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confirmed_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[SlotStatus] = mapped_column(
        enum_column(SlotStatus),
        default=SlotStatus.OPEN,
        nullable=False,
    )
    # Optimistic-concurrency counter (incremented on every inventory mutation).
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    experience: Mapped[Experience] = relationship(back_populates="slots")

    @property
    def available_quantity(self) -> int:
        """Units still bookable = capacity - reserved - confirmed."""
        return self.capacity - self.reserved_quantity - self.confirmed_quantity
