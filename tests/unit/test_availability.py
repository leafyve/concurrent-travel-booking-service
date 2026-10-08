"""Unit tests for slot availability calculation (pure property, no DB)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.time import utcnow
from app.models.experience import ExperienceSlot

pytestmark = pytest.mark.unit


def _slot(capacity: int, reserved: int, confirmed: int) -> ExperienceSlot:
    start = utcnow() + timedelta(days=1)
    return ExperienceSlot(
        starts_at=start,
        ends_at=start + timedelta(hours=1),
        capacity=capacity,
        reserved_quantity=reserved,
        confirmed_quantity=confirmed,
    )


def test_available_quantity() -> None:
    assert _slot(10, 3, 2).available_quantity == 5
    assert _slot(5, 5, 0).available_quantity == 0
    assert _slot(5, 2, 3).available_quantity == 0


def test_available_quantity_full() -> None:
    assert _slot(4, 0, 4).available_quantity == 0
