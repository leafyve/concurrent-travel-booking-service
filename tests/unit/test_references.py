"""Unit tests for booking-reference generation."""

from __future__ import annotations

import re

import pytest

from app.domain.references import generate_booking_reference

pytestmark = pytest.mark.unit

_PATTERN = re.compile(r"^BKG-[2-9A-HJ-NP-Z]{8}$")


def test_reference_format() -> None:
    assert _PATTERN.match(generate_booking_reference())


def test_references_are_unique_enough() -> None:
    refs = {generate_booking_reference() for _ in range(2000)}
    # Collisions across 2000 draws from 31^8 space should not happen.
    assert len(refs) == 2000


def test_no_ambiguous_characters() -> None:
    ref = generate_booking_reference()
    body = ref.split("-", 1)[1]
    assert not set(body) & set("01OIL")
