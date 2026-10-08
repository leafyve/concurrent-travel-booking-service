"""Liveness and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.api.dependencies.db import SessionDep

router = APIRouter(tags=["health"])


@router.get("/health/live", summary="Liveness probe")
async def live() -> dict[str, str]:
    """Process is up (no dependencies checked)."""
    return {"status": "alive"}


@router.get("/health/ready", summary="Readiness probe")
async def ready(session: SessionDep, response: Response) -> dict[str, str]:
    """Ready only if the database answers a trivial query."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        response.status_code = 503
        return {"status": "unready", "database": "unavailable"}
    return {"status": "ready", "database": "ok"}
