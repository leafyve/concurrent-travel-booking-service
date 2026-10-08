"""Exception handlers producing RFC 7807 problem documents.

Every failure — expected domain errors, request validation, unmatched routes,
and unexpected exceptions — is rendered as a consistent, safe
``application/problem+json`` body. Stack traces and database internals are logged
server-side but **never** returned to the client.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import AppError
from app.observability.logging import get_logger
from app.schemas.errors import ProblemDetail

_PROBLEM_MEDIA_TYPE = "application/problem+json"
_logger = get_logger("errors")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _problem_response(
    request: Request,
    *,
    status: int,
    title: str,
    error_code: str,
    detail: str,
    field_errors: dict[str, str] | None = None,
) -> JSONResponse:
    problem = ProblemDetail(
        title=title,
        status=status,
        detail=detail,
        error_code=error_code,
        request_id=_request_id(request),
        field_errors=field_errors,
    )
    return JSONResponse(
        status_code=status,
        content=problem.model_dump(exclude_none=True),
        media_type=_PROBLEM_MEDIA_TYPE,
    )


async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    log = _logger.warning if exc.status < 500 else _logger.error
    log("request.error", error_code=exc.error_code, status=exc.status, detail=exc.detail)
    return _problem_response(
        request,
        status=exc.status,
        title=exc.title,
        error_code=exc.error_code,
        detail=exc.detail,
        field_errors=exc.field_errors,
    )


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    field_errors: dict[str, str] = {}
    for err in exc.errors():
        location = ".".join(str(p) for p in err["loc"][1:]) or err["loc"][0]
        field_errors[str(location)] = err["msg"]
    return _problem_response(
        request,
        status=422,
        title="Validation Failed",
        error_code="validation_failed",
        detail="One or more request fields are invalid.",
        field_errors=field_errors,
    )


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _problem_response(
        request,
        status=exc.status_code,
        title=exc.detail if isinstance(exc.detail, str) else "HTTP Error",
        error_code=f"http_{exc.status_code}",
        detail=exc.detail if isinstance(exc.detail, str) else "Request could not be completed.",
    )


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    # Log with traceback server-side; return an opaque 500 to the client.
    _logger.error("request.unhandled_exception", error=str(exc), exc_info=True)
    return _problem_response(
        request,
        status=500,
        title="Internal Server Error",
        error_code="internal_error",
        detail="An unexpected error occurred. The incident has been logged.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _handle_unexpected)
