"""Unit tests for Decimal money arithmetic and per-currency minor units."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.money import (
    UnsupportedCurrencyError,
    compute_total,
    from_minor_units,
    minor_unit_exponent,
    quantize_amount,
    to_minor_units,
)

pytestmark = pytest.mark.unit


def test_two_decimal_currency_quantization() -> None:
    assert quantize_amount(Decimal("80.005"), "SGD") == Decimal("80.01")
    assert compute_total(Decimal("68.00"), 3, "SGD") == Decimal("204.00")


def test_zero_decimal_currencies() -> None:
    assert minor_unit_exponent("JPY") == 0
    assert minor_unit_exponent("KRW") == 0
    assert compute_total(Decimal("9800"), 2, "JPY") == Decimal("19600")
    assert to_minor_units(Decimal("9800"), "JPY") == 9800


def test_minor_units_roundtrip_two_decimal() -> None:
    assert to_minor_units(Decimal("1500.00"), "THB") == 150000
    assert from_minor_units(150000, "THB") == Decimal("1500.00")


def test_unsupported_currency() -> None:
    with pytest.raises(UnsupportedCurrencyError):
        minor_unit_exponent("XYZ")


def test_compute_total_rejects_non_positive_quantity() -> None:
    with pytest.raises(ValueError, match="positive"):
        compute_total(Decimal("10.00"), 0, "SGD")


@given(
    unit=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("100000"), places=2),
    qty=st.integers(min_value=1, max_value=50),
)
def test_total_equals_quantized_product(unit: Decimal, qty: int) -> None:
    # Property: total is exactly the quantized unit*qty (no float drift).
    expected = quantize_amount(unit * Decimal(qty), "SGD")
    assert compute_total(unit, qty, "SGD") == expected


@given(minor=st.integers(min_value=0, max_value=10_000_000))
def test_minor_unit_roundtrip_property(minor: int) -> None:
    # Property: converting to minor units and back is lossless.
    amount = from_minor_units(minor, "SGD")
    assert to_minor_units(amount, "SGD") == minor
