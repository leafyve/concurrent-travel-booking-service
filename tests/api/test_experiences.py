"""API tests for experience search and availability."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.enums import UserRole
from tests.factories import (
    create_experience,
    create_merchant,
    create_slot,
    create_user,
)

pytestmark = pytest.mark.api


async def _merchant(db_session):
    owner = await create_user(db_session, role=UserRole.MERCHANT)
    return await create_merchant(db_session, owner=owner)


async def test_search_returns_published_experiences(client, db_session) -> None:
    merchant = await _merchant(db_session)
    await create_experience(db_session, merchant=merchant, destination="Tokyo")
    resp = await client.get("/api/v1/experiences")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert body["limit"] == 20


async def test_search_filters_by_destination(client, db_session) -> None:
    merchant = await _merchant(db_session)
    await create_experience(db_session, merchant=merchant, destination="Seoul")
    await create_experience(db_session, merchant=merchant, destination="Bangkok")
    resp = await client.get("/api/v1/experiences", params={"destination": "seoul"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["destination"] == "Seoul"


async def test_search_min_capacity_excludes_full_slots(client, db_session) -> None:
    merchant = await _merchant(db_session)
    exp = await create_experience(db_session, merchant=merchant, destination="Osaka")
    await create_slot(db_session, experience=exp, capacity=3, confirmed=3)
    # No availability → excluded when requiring capacity.
    resp = await client.get(
        "/api/v1/experiences",
        params={"destination": "osaka", "min_available_capacity": 1},
    )
    assert resp.json()["total"] == 0


async def test_pagination(client, db_session) -> None:
    merchant = await _merchant(db_session)
    for _ in range(5):
        await create_experience(db_session, merchant=merchant, destination="Paginate")
    resp = await client.get(
        "/api/v1/experiences",
        params={"destination": "paginate", "limit": 2, "offset": 0},
    )
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2


async def test_experience_detail_404(client) -> None:
    resp = await client.get("/api/v1/experiences/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "not_found"


async def test_slots_availability_hides_internal_fields(client, db_session) -> None:
    merchant = await _merchant(db_session)
    exp = await create_experience(db_session, merchant=merchant, base_price=Decimal("50.00"))
    await create_slot(db_session, experience=exp, capacity=10, reserved=2, confirmed=1)
    resp = await client.get(f"/api/v1/experiences/{exp.id}/slots")
    assert resp.status_code == 200
    slot = resp.json()[0]
    assert slot["total_capacity"] == 10
    assert slot["available_capacity"] == 7
    assert slot["price"] == "50.00"
    # Internal reservation counters must not be exposed.
    assert "reserved_quantity" not in slot
    assert "confirmed_quantity" not in slot
