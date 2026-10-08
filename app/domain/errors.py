"""Typed domain error hierarchy.

Services raise these framework-agnostic errors; a single FastAPI exception
handler (:mod:`app.api.errors`) translates them into RFC 7807 problem
documents. Keeping the taxonomy here means business rules never import
Starlette/HTTP concepts.

Each error carries a stable, machine-readable ``error_code`` (used by clients
and tests) plus a default HTTP status the API layer applies.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for all expected, client-facing domain errors.

    ``error_code`` is a stable identifier; ``status`` is the HTTP status the API
    layer maps to; ``detail`` is a human-readable, non-sensitive explanation.
    """

    error_code: str = "internal_error"
    status: int = 500
    title: str = "Internal Server Error"

    def __init__(
        self,
        detail: str | None = None,
        *,
        field_errors: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.detail = detail or self.title
        self.field_errors = field_errors
        self.extra = extra or {}
        super().__init__(self.detail)


# --- 400 / 422 ------------------------------------------------------------
class ValidationFailedError(AppError):
    error_code = "validation_failed"
    status = 422
    title = "Validation Failed"


class BadRequestError(AppError):
    error_code = "bad_request"
    status = 400
    title = "Bad Request"


# --- 401 / 403 ------------------------------------------------------------
class AuthenticationError(AppError):
    error_code = "unauthenticated"
    status = 401
    title = "Authentication Required"


class AuthorizationError(AppError):
    error_code = "forbidden"
    status = 403
    title = "Forbidden"


# --- 404 ------------------------------------------------------------------
class NotFoundError(AppError):
    error_code = "not_found"
    status = 404
    title = "Resource Not Found"


# --- 409 (conflict family) ------------------------------------------------
class ConflictError(AppError):
    error_code = "conflict"
    status = 409
    title = "Conflict"


class InventoryConflictError(ConflictError):
    """Not enough available capacity to satisfy the request."""

    error_code = "inventory_unavailable"
    title = "Inventory Unavailable"


class IdempotencyConflictError(ConflictError):
    """Same idempotency key reused with a *different* request payload."""

    error_code = "idempotency_key_conflict"
    title = "Idempotency Key Conflict"


class ReservationExpiredError(ConflictError):
    error_code = "reservation_expired"
    title = "Reservation Expired"


class ReservationNotActiveError(ConflictError):
    error_code = "reservation_not_active"
    title = "Reservation Not Active"


class DuplicateBookingError(ConflictError):
    error_code = "reservation_already_booked"
    title = "Reservation Already Booked"


class CapacityBelowCommittedError(ConflictError):
    """Merchant tried to set capacity below confirmed + reserved inventory."""

    error_code = "capacity_below_committed"
    title = "Capacity Below Committed Inventory"


class StateTransitionError(ConflictError):
    error_code = "invalid_state_transition"
    title = "Invalid State Transition"


# --- Webhook-specific -----------------------------------------------------
class WebhookSignatureError(AppError):
    error_code = "invalid_webhook_signature"
    status = 401
    title = "Invalid Webhook Signature"


class WebhookReplayError(AppError):
    error_code = "webhook_timestamp_out_of_window"
    status = 400
    title = "Webhook Timestamp Outside Replay Window"


class PaymentAmountMismatchError(AppError):
    error_code = "payment_amount_mismatch"
    status = 409
    title = "Payment Amount Or Currency Mismatch"
