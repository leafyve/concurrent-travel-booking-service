"""Unit tests for webhook HMAC signatures and replay window."""

from __future__ import annotations

import pytest

from app.domain.signatures import (
    compute_signature,
    is_within_replay_window,
    verify_signature,
)

pytestmark = pytest.mark.unit

SECRET = "test-secret"
BODY = b'{"event_id":"evt_1","amount_minor":100}'
TS = 1_700_000_000


def test_valid_signature_verifies() -> None:
    sig = compute_signature(SECRET, TS, BODY)
    assert verify_signature(SECRET, TS, BODY, sig) is True


def test_tampered_body_fails() -> None:
    sig = compute_signature(SECRET, TS, BODY)
    assert verify_signature(SECRET, TS, BODY + b"x", sig) is False


def test_wrong_secret_fails() -> None:
    sig = compute_signature(SECRET, TS, BODY)
    assert verify_signature("other-secret", TS, BODY, sig) is False


def test_wrong_timestamp_fails() -> None:
    sig = compute_signature(SECRET, TS, BODY)
    assert verify_signature(SECRET, TS + 1, BODY, sig) is False


def test_replay_window() -> None:
    assert is_within_replay_window(TS, TS + 100, 300) is True
    assert is_within_replay_window(TS, TS + 400, 300) is False
    # Future timestamps beyond the window are also rejected.
    assert is_within_replay_window(TS, TS - 400, 300) is False
