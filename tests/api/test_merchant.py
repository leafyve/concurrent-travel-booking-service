"""API tests for merchant inventory synchronisation."""

from __future__ import annotations

import uuid

import pytest

from app.domain.enums import UserRole
from app.models.user import User
from tests.factories import (
    auth_header,
    create_experience,
    create_merchant,
    create_slot,
    create_user,
)

pytestmark = pytest.mark.api


async def _merchant_with_slot(db_session, *, capacity=10, reserved=0, confirmed=0):
    owner = await create_user(db_session, role=UserRole.MERCHANT)
    merchant = await create_merchant(db_session, owner=owner)
    experience = await create_experience(db_session, merchant=merchant)
    slot = await create_slot(
        db_session,
        experience=experience,
        capacity=capacity,
        reserved=reserved,
        confirmed=confirmed,
    )
    return owner, slot


async def test_accept_capacity_increase(client, db_session) -> None:
    owner, slot = await _merchant_with_slot(db_session, capacity=10)
    resp = await client.post(
        "/api/v1/merchant/inventory-updates",
        json={
            "external_update_id": "ext-1",
            "slot_id": str(slot.id),
            "requested_capacity": 25,
        },
        headers=auth_header(owner),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["validation_result"]["new_capacity"] == 25


async def test_reject_capacity_below_committed(client, db_session) -> None:
    owner, slot = await _merchant_with_slot(db_session, capacity=10, confirmed=6)
    resp = await client.post(
        "/api/v1/merchant/inventory-updates",
        json={
            "external_update_id": "ext-2",
            "slot_id": str(slot.id),
            "requested_capacity": 4,  # below 6 committed
        },
        headers=auth_header(owner),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["validation_result"]["reason"] == "capacity_below_committed"


async def test_cannot_update_another_merchants_slot(client, db_session) -> None:
    _owner_a, slot_a = await _merchant_with_slot(db_session)
    owner_b = await create_user(db_session, role=UserRole.MERCHANT)
    await create_merchant(db_session, owner=owner_b)
    resp = await client.post(
        "/api/v1/merchant/inventory-updates",
        json={
            "external_update_id": "ext-3",
            "slot_id": str(slot_a.id),
            "requested_capacity": 5,
        },
        headers=auth_header(owner_b),
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "forbidden"


async def test_duplicate_external_update_id_is_idempotent(client, db_session) -> None:
    owner, slot = await _merchant_with_slot(db_session, capacity=10)
    payload = {
        "external_update_id": "ext-dup",
        "slot_id": str(slot.id),
        "requested_capacity": 15,
    }
    first = await client.post(
        "/api/v1/merchant/inventory-updates", json=payload, headers=auth_header(owner)
    )
    # Resend with a different capacity but same external id → original replayed.
    payload2 = {**payload, "requested_capacity": 99}
    second = await client.post(
        "/api/v1/merchant/inventory-updates", json=payload2, headers=auth_header(owner)
    )
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["requested_capacity"] == 15


async def test_unknown_slot_404(client, db_session) -> None:
    owner = await create_user(db_session, role=UserRole.MERCHANT)
    await create_merchant(db_session, owner=owner)
    resp = await client.post(
        "/api/v1/merchant/inventory-updates",
        json={
            "external_update_id": "ext-4",
            "slot_id": str(uuid.uuid4()),
            "requested_capacity": 5,
        },
        headers=auth_header(owner),
    )
    assert resp.status_code == 404


async def test_user_without_merchant_account_forbidden(client, db_session) -> None:
    # A user with the MERCHANT role but no merchant row.
    lonely = User(
        email=f"lonely-{uuid.uuid4().hex[:6]}@example.test",
        password_hash="x",
        role=UserRole.MERCHANT,
        is_active=True,
    )
    db_session.add(lonely)
    await db_session.commit()
    resp = await client.post(
        "/api/v1/merchant/inventory-updates",
        json={
            "external_update_id": "ext-5",
            "slot_id": str(uuid.uuid4()),
            "requested_capacity": 5,
        },
        headers=auth_header(lonely),
    )
    assert resp.status_code == 403
