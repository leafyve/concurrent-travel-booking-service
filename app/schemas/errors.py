"""RFC 7807-inspired problem detail schema."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProblemDetail(BaseModel):
    """A consistent, safe error envelope returned for every failure.

    Modeled on RFC 7807 with a few pragmatic additions (``error_code``,
    ``request_id``, ``field_errors``) that make client handling and support
    triage easier. Never contains stack traces or database internals.
    """

    model_config = ConfigDict(extra="forbid")

    type: str = Field(default="about:blank", description="A URI/identifier for the problem type.")
    title: str = Field(description="Short, human-readable summary.")
    status: int = Field(description="HTTP status code.")
    detail: str = Field(description="Human-readable explanation for this occurrence.")
    error_code: str = Field(description="Stable machine-readable error code.")
    request_id: str = Field(description="Correlation id for tracing this request.")
    field_errors: dict[str, str] | None = Field(
        default=None,
        description="Per-field validation messages, when applicable.",
    )
