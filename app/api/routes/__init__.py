"""API route aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    auth,
    bookings,
    experiences,
    health,
    merchant,
    reservations,
    webhooks,
)

# Versioned business API.
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(experiences.router)
api_router.include_router(reservations.router)
api_router.include_router(bookings.router)
api_router.include_router(merchant.router)
api_router.include_router(webhooks.router)

# Unversioned operational endpoints (health) are mounted directly in main.
health_router = health.router
