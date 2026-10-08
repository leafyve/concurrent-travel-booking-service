"""Human-readable booking references.

Booking references are shown to customers and support staff, so they avoid
ambiguous characters (0/O, 1/I/L). Uniqueness is *enforced by the database*
(a UNIQUE constraint); this generator only makes collisions astronomically
unlikely so the insert rarely needs to retry.
"""

from __future__ import annotations

import secrets

# Crockford-style alphabet without visually ambiguous characters.
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_REFERENCE_LENGTH = 8
_PREFIX = "BKG"


def generate_booking_reference() -> str:
    """Return a reference like ``BKG-7Q2K9F4A``."""
    body = "".join(secrets.choice(_ALPHABET) for _ in range(_REFERENCE_LENGTH))
    return f"{_PREFIX}-{body}"
