"""Timezone-aware time helpers.

The entire codebase uses **timezone-aware UTC** datetimes. Naive datetimes are
banned by Ruff's ``DTZ`` rules; this module is the single source for "now".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def in_minutes(minutes: float) -> datetime:
    """Return a UTC datetime ``minutes`` in the future."""
    return utcnow() + timedelta(minutes=minutes)


def is_past(moment: datetime) -> bool:
    """Return True if ``moment`` is strictly in the past (UTC-aware)."""
    return moment <= utcnow()
