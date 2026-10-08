"""Password hashing and JWT access-token helpers.

* Passwords are hashed with **bcrypt** (per-password random salt).
* Access tokens are short-lived **JWT (HS256)** bearer tokens.

No secret ever appears in a log line — see :mod:`app.observability.logging`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.time import utcnow

# bcrypt truncates silently at 72 bytes; we reject longer inputs explicitly so
# two different long passwords can never collide.
_BCRYPT_MAX_BYTES = 72


def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt, returning the encoded digest."""
    pw_bytes = plain.encode("utf-8")
    if len(pw_bytes) > _BCRYPT_MAX_BYTES:
        raise ValueError("password must not exceed 72 bytes")
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if ``plain`` matches the bcrypt ``hashed`` digest."""
    pw_bytes = plain.encode("utf-8")
    if len(pw_bytes) > _BCRYPT_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(pw_bytes, hashed.encode("utf-8"))
    except ValueError:
        # Malformed hash string — treat as a non-match rather than crashing.
        return False


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Decoded, validated JWT claims for an authenticated actor."""

    subject: str
    role: str
    token_id: str


def create_access_token(
    *,
    subject: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed, short-lived JWT access token.

    ``subject`` is the user id; ``role`` is the coarse authorization role.
    """
    settings = get_settings()
    now = utcnow()
    expire = now + (expires_delta or timedelta(minutes=settings.access_token_expires_minutes))
    payload = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenClaims:
    """Decode and validate a JWT access token.

    Raises :class:`jwt.PyJWTError` subclasses on any validation failure
    (expiry, bad signature, malformed token).
    """
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub", "role"]},
    )
    return TokenClaims(
        subject=str(payload["sub"]),
        role=str(payload["role"]),
        token_id=str(payload.get("jti", "")),
    )
