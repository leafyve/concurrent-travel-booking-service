"""Booking and PaymentAttempt models.

Two database-level invariants matter here:

* ``booking.reservation_id`` is **UNIQUE** — one reservation can produce at most
  one booking (invariant: no double booking).
* ``payment_attempts.event_id`` is **UNIQUE** — a provider webhook event can be
  recorded at most once (invariant: webhook events are applied at most once).
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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.domain.enums import BookingStatus, PaymentStatus
from app.models._columns import enum_column


class Booking(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_bookings_customer", "customer_id"),
        Index("ix_bookings_slot", "slot_id"),
    )

    booking_reference: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    # UNIQUE: enforces "one reservation -> at most one booking".
    reservation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reservations.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    slot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experience_slots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[BookingStatus] = mapped_column(
        enum_column(BookingStatus),
        default=BookingStatus.PENDING_PAYMENT,
        nullable=False,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaymentAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payment_attempts"
    __table_args__ = (
        # NULL event_id allowed (the initial "pending" attempt); once set it is
        # globally unique so a webhook event cannot be applied twice.
        Index(
            "uq_payment_attempts_event_id",
            "event_id",
            unique=True,
            postgresql_where="event_id IS NOT NULL",
        ),
        Index("ix_payment_attempts_booking", "booking_id"),
    )

    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        enum_column(PaymentStatus),
        default=PaymentStatus.PENDING,
        nullable=False,
    )
    event_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
