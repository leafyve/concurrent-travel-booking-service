"""Unit tests for cancellation policy rules."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from app.core.time import utcnow
from app.domain.enums import CancellationPolicy
from app.domain.policies import evaluate_cancellation

pytestmark = pytest.mark.unit

AMOUNT = Decimal("100.00")
CURRENCY = "SGD"


def _evaluate(policy: CancellationPolicy, hours_to_start: float):
    now = utcnow()
    return evaluate_cancellation(
        policy=policy,
        now=now,
        slot_starts_at=now + timedelta(hours=hours_to_start),
        amount_paid=AMOUNT,
        currency=CURRENCY,
    )


def test_non_refundable_never_refunds() -> None:
    outcome = _evaluate(CancellationPolicy.NON_REFUNDABLE, 100)
    assert outcome.refundable is False
    assert outcome.refund_amount == Decimal("0.00")


def test_flexible_until_start_refunds_before_start() -> None:
    assert _evaluate(CancellationPolicy.FLEXIBLE_UNTIL_START, 1).refundable is True


def test_flexible_until_start_no_refund_after_start() -> None:
    outcome = _evaluate(CancellationPolicy.FLEXIBLE_UNTIL_START, -1)
    assert outcome.refundable is False
    assert outcome.refund_amount == Decimal("0.00")


def test_fully_refundable_before_cutoff() -> None:
    outcome = _evaluate(CancellationPolicy.FULLY_REFUNDABLE_UNTIL_24_HOURS, 48)
    assert outcome.refundable is True
    assert outcome.refund_amount == AMOUNT


def test_fully_refundable_within_cutoff() -> None:
    outcome = _evaluate(CancellationPolicy.FULLY_REFUNDABLE_UNTIL_24_HOURS, 12)
    assert outcome.refundable is False
    assert outcome.refund_amount == Decimal("0.00")


def test_fully_refundable_exactly_at_cutoff_is_refundable() -> None:
    # now <= start - 24h → exactly 24h ahead should still refund.
    assert _evaluate(CancellationPolicy.FULLY_REFUNDABLE_UNTIL_24_HOURS, 24).refundable
