"""Explicit status enumerations used across the domain.

Using string enums (rather than free-form strings) keeps state machines
explicit, gives mypy something to check, and makes the values self-documenting
in the database and API payloads.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    CUSTOMER = "customer"
    MERCHANT = "merchant"
    ADMIN = "admin"


class MerchantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class ExperienceStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class SlotStatus(StrEnum):
    OPEN = "open"
    SOLD_OUT = "sold_out"
    CLOSED = "closed"


class ReservationStatus(StrEnum):
    ACTIVE = "active"
    CONVERTED = "converted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class BookingStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"
    CONFIRMED = "confirmed"
    CANCELLATION_PENDING = "cancellation_pending"
    CANCELLED = "cancelled"
    PAYMENT_FAILED = "payment_failed"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CancellationPolicy(StrEnum):
    FULLY_REFUNDABLE_UNTIL_24_HOURS = "fully_refundable_until_24_hours"
    NON_REFUNDABLE = "non_refundable"
    FLEXIBLE_UNTIL_START = "flexible_until_start"


class PartnerUpdateStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"
