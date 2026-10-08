"""Cancellation policy rules.

A policy decides, at cancellation time, whether the customer is refunded and how
much. These are **pure functions** of (policy, now, slot start, amount paid) so
they are trivially unit- and property-testable.

Note: inventory is *always* restored on cancellation regardless of refund
eligibility — the refund decision is a financial concern, not an inventory one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from app.domain.enums import CancellationPolicy
from app.domain.money import quantize_amount

REFUND_CUTOFF_HOURS = 24


@dataclass(frozen=True, slots=True)
class CancellationOutcome:
    """Result of evaluating a cancellation policy."""

    refundable: bool
    refund_amount: Decimal
    reason: str


def evaluate_cancellation(
    *,
    policy: CancellationPolicy,
    now: datetime,
    slot_starts_at: datetime,
    amount_paid: Decimal,
    currency: str,
) -> CancellationOutcome:
    """Evaluate whether a cancellation is refundable under ``policy``.

    All datetimes must be timezone-aware and comparable (UTC recommended).
    """
    zero = quantize_amount(Decimal(0), currency)

    if policy is CancellationPolicy.NON_REFUNDABLE:
        return CancellationOutcome(
            refundable=False,
            refund_amount=zero,
            reason="Policy is non-refundable.",
        )

    if policy is CancellationPolicy.FLEXIBLE_UNTIL_START:
        if now < slot_starts_at:
            return CancellationOutcome(
                refundable=True,
                refund_amount=quantize_amount(amount_paid, currency),
                reason="Cancelled before the experience start time.",
            )
        return CancellationOutcome(
            refundable=False,
            refund_amount=zero,
            reason="Cancelled after the experience start time.",
        )

    if policy is CancellationPolicy.FULLY_REFUNDABLE_UNTIL_24_HOURS:
        cutoff = slot_starts_at - timedelta(hours=REFUND_CUTOFF_HOURS)
        if now <= cutoff:
            return CancellationOutcome(
                refundable=True,
                refund_amount=quantize_amount(amount_paid, currency),
                reason=f"Cancelled at least {REFUND_CUTOFF_HOURS}h before start.",
            )
        return CancellationOutcome(
            refundable=False,
            refund_amount=zero,
            reason=f"Cancelled within {REFUND_CUTOFF_HOURS}h of start.",
        )

    # Exhaustiveness guard: a new enum member without a branch fails loudly.
    raise ValueError(f"unhandled cancellation policy: {policy!r}")  # pragma: no cover
