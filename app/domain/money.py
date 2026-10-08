"""Decimal money arithmetic with per-currency minor units.

**All monetary values use :class:`decimal.Decimal`** — never binary floating
point — so prices, totals and refunds are exact. Payment providers represent
amounts as integers in a currency's *minor units* (e.g. cents), so we support
converting to/from that representation for webhook amount matching.

Currencies differ in how many decimal places they use:

* ``SGD``, ``THB``, ``USD`` → 2 minor units (cents)
* ``JPY``, ``KRW``          → 0 minor units (no fractional unit)
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# ISO 4217 subset relevant to the seeded destinations, with minor-unit exponents.
CURRENCY_MINOR_UNITS: dict[str, int] = {
    "SGD": 2,
    "THB": 2,
    "USD": 2,
    "JPY": 0,
    "KRW": 0,
}


class UnsupportedCurrencyError(ValueError):
    """Raised when a currency is not in the supported registry."""


def minor_unit_exponent(currency: str) -> int:
    """Return the number of decimal places used by ``currency``."""
    code = currency.upper()
    if code not in CURRENCY_MINOR_UNITS:
        raise UnsupportedCurrencyError(f"unsupported currency: {currency!r}")
    return CURRENCY_MINOR_UNITS[code]


def _quantum(currency: str) -> Decimal:
    exponent = minor_unit_exponent(currency)
    return Decimal(1).scaleb(-exponent)  # e.g. exponent 2 -> Decimal("0.01")


def quantize_amount(amount: Decimal, currency: str) -> Decimal:
    """Round ``amount`` to the currency's minor unit using half-up rounding."""
    return amount.quantize(_quantum(currency), rounding=ROUND_HALF_UP)


def compute_total(unit_price: Decimal, quantity: int, currency: str) -> Decimal:
    """Compute ``unit_price * quantity`` exactly, quantized to the currency.

    ``quantity`` must be a positive integer.
    """
    if quantity <= 0:
        raise ValueError("quantity must be a positive integer")
    return quantize_amount(unit_price * Decimal(quantity), currency)


def to_minor_units(amount: Decimal, currency: str) -> int:
    """Convert a Decimal amount to an integer number of minor units.

    Used to match webhook amounts, which providers send as integers.
    """
    quantized = quantize_amount(amount, currency)
    exponent = minor_unit_exponent(currency)
    return int((quantized.scaleb(exponent)).to_integral_value(rounding=ROUND_HALF_UP))


def from_minor_units(minor: int, currency: str) -> Decimal:
    """Convert an integer number of minor units back to a Decimal amount."""
    exponent = minor_unit_exponent(currency)
    return quantize_amount(Decimal(minor).scaleb(-exponent), currency)
