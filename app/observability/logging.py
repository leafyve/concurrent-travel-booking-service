"""Structured JSON logging with request correlation.

Every log line carries a ``request_id`` (and the authenticated actor id when
known) via structlog context variables. A middleware assigns the id, times the
request, records HTTP metrics, and emits one access log line per request.

**Secrets are never logged.** We only ever log identifiers, not tokens,
passwords, signatures, or raw payment payloads.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS

REQUEST_ID_HEADER = "X-Request-ID"


def configure_logging(*, json_logs: bool = True, level: str = "INFO") -> None:
    """Configure structlog + stdlib logging once at startup."""
    logging.basicConfig(format="%(message)s", level=getattr(logging, level.upper(), logging.INFO))

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


def new_request_id() -> str:
    return uuid.uuid4().hex


def _route_template(request: Request) -> str:
    """Return the low-cardinality route template for metric labels."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path or request.url.path


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns request ids, times requests, and records access logs + metrics."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming or new_request_id()
        request.state.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        logger = get_logger("http")
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration = time.perf_counter() - start
            route = _route_template(request)
            actor_id = getattr(request.state, "actor_id", None)
            HTTP_REQUESTS.labels(request.method, route, str(status_code)).inc()
            HTTP_REQUEST_DURATION.labels(request.method, route).observe(duration)
            logger.info(
                "request.completed",
                route=route,
                status=status_code,
                duration_ms=round(duration * 1000, 2),
                actor_id=str(actor_id) if actor_id else None,
            )
            structlog.contextvars.clear_contextvars()
