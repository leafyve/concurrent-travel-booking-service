"""Unit tests for request fingerprinting (idempotency payload hashing)."""

from __future__ import annotations

import pytest

from app.domain.fingerprint import canonical_json, request_fingerprint

pytestmark = pytest.mark.unit


def test_key_order_does_not_change_fingerprint() -> None:
    a = {"slot_id": "x", "quantity": 2}
    b = {"quantity": 2, "slot_id": "x"}
    assert request_fingerprint(a) == request_fingerprint(b)


def test_different_payload_changes_fingerprint() -> None:
    a = {"slot_id": "x", "quantity": 2}
    b = {"slot_id": "x", "quantity": 3}
    assert request_fingerprint(a) != request_fingerprint(b)


def test_fingerprint_is_stable_sha256_hex() -> None:
    fp = request_fingerprint({"a": 1})
    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)


def test_canonical_json_is_compact_and_sorted() -> None:
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'
