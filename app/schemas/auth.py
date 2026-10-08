"""Authentication schemas."""

from __future__ import annotations

import uuid

from pydantic import Field

from app.domain.enums import UserRole
from app.schemas.common import ApiModel


class LoginRequest(ApiModel):
    # Emails are treated as opaque identifiers here; we validate length/shape but
    # avoid strict deliverability checks (which reject example/test domains).
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=72)


class TokenResponse(ApiModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access-token lifetime in seconds.")


class UserOut(ApiModel):
    id: uuid.UUID
    email: str
    role: UserRole
    is_active: bool
