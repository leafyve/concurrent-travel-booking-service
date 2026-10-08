"""Unit tests for password hashing and JWT tokens."""

from __future__ import annotations

from datetime import timedelta

import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

pytestmark = pytest.mark.unit


def test_password_hash_verifies() -> None:
    hashed = hash_password("s3cret-password")
    assert hashed != "s3cret-password"
    assert verify_password("s3cret-password", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_password_over_72_bytes_rejected() -> None:
    with pytest.raises(ValueError, match="72"):
        hash_password("a" * 73)
    # Verification of an over-long password is a non-match, not a crash.
    assert verify_password("a" * 73, hash_password("short")) is False


def test_jwt_roundtrip() -> None:
    token = create_access_token(subject="user-1", role="customer")
    claims = decode_access_token(token)
    assert claims.subject == "user-1"
    assert claims.role == "customer"
    assert claims.token_id


def test_expired_token_rejected() -> None:
    token = create_access_token(
        subject="user-1", role="customer", expires_delta=timedelta(seconds=-1)
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_tampered_token_rejected() -> None:
    token = create_access_token(subject="user-1", role="customer")
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token + "tamper")
