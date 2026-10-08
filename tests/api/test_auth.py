"""API tests for authentication and authorization."""

from __future__ import annotations

import pytest

from app.domain.enums import UserRole
from tests.factories import DEFAULT_PASSWORD, auth_header, create_user

pytestmark = pytest.mark.api


async def test_login_success(client, db_session) -> None:
    user = await create_user(db_session, role=UserRole.CUSTOMER)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": DEFAULT_PASSWORD},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_login_wrong_password(client, db_session) -> None:
    user = await create_user(db_session, role=UserRole.CUSTOMER)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "unauthenticated"


async def test_login_unknown_user(client) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.test", "password": "whatever"},
    )
    assert resp.status_code == 401


async def test_inactive_user_cannot_login(client, db_session) -> None:
    user = await create_user(db_session, role=UserRole.CUSTOMER, is_active=False)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": DEFAULT_PASSWORD},
    )
    assert resp.status_code == 401


async def test_me_requires_auth(client) -> None:
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "unauthenticated"


async def test_me_returns_current_user(client, db_session) -> None:
    user = await create_user(db_session, role=UserRole.MERCHANT)
    resp = await client.get("/api/v1/auth/me", headers=auth_header(user))
    assert resp.status_code == 200
    assert resp.json()["role"] == "merchant"


async def test_role_gate_blocks_wrong_role(client, db_session) -> None:
    # A customer may not call the merchant endpoint.
    customer = await create_user(db_session, role=UserRole.CUSTOMER)
    resp = await client.post(
        "/api/v1/merchant/inventory-updates",
        json={
            "external_update_id": "x",
            "slot_id": "00000000-0000-0000-0000-000000000000",
            "requested_capacity": 5,
        },
        headers=auth_header(customer),
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "forbidden"


async def test_malformed_token_rejected(client) -> None:
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
