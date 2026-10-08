"""FastAPI application factory.

Wires together middleware (request correlation + metrics), the versioned API
router, operational endpoints (health, metrics), RFC 7807 error handling, and
graceful engine disposal on shutdown.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import Response

from app.api.errors import register_exception_handlers
from app.api.routes import api_router, health_router
from app.core.config import get_settings
from app.db.session import dispose_engine
from app.observability.logging import RequestContextMiddleware, configure_logging
from app.observability.metrics import render_latest


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(json_logs=settings.log_json, level=settings.log_level)
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        summary=(
            "Independent educational portfolio backend for concurrent travel-"
            "experience inventory and booking orchestration. Not affiliated with Klook."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(api_router)

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        payload, content_type = render_latest()
        return Response(content=payload, media_type=content_type)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "docs": "/docs",
            "health": "/health/ready",
            "metrics": "/metrics",
            "disclaimer": "Independent educational project. Not affiliated with Klook.",
        }

    return app


app = create_app()
