"""Shared column helpers for models."""

from __future__ import annotations

from enum import StrEnum
from typing import TypeVar

from sqlalchemy import Enum as SAEnum

_E = TypeVar("_E", bound=StrEnum)


def enum_column(enum_cls: type[_E]) -> SAEnum:
    """Return a portable, non-native Enum column storing the *values*.

    ``native_enum=False`` renders as ``VARCHAR`` + a CHECK constraint (easy for
    Alembic and portable across databases); ``values_callable`` ensures we store
    the lowercase string values (e.g. ``'customer'``) rather than member names.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda e: [member.value for member in e],
        validate_strings=True,
    )
