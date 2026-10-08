"""Shared schema primitives."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiModel(BaseModel):
    """Base for all API schemas (strict, ORM-friendly)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class Page(ApiModel, Generic[T]):
    """A page of results with total count and paging echo."""

    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class MessageResponse(ApiModel):
    message: str
