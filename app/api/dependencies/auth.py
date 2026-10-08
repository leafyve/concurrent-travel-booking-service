"""Authentication & authorization dependencies.

Bearer JWTs are decoded from claims only (no DB round-trip); tokens are
short-lived. Role dependencies gate endpoints, and services perform per-resource
ownership checks.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_access_token
from app.domain.enums import UserRole
from app.domain.errors import AuthenticationError, AuthorizationError, BadRequestError

_bearer = HTTPBearer(auto_error=False, description="JWT access token.")


@dataclass(frozen=True, slots=True)
class CurrentActor:
    id: uuid.UUID
    role: UserRole


async def get_current_actor(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentActor:
    if credentials is None:
        raise AuthenticationError("Missing bearer token.")
    try:
        claims = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired token.") from exc
    try:
        actor = CurrentActor(id=uuid.UUID(claims.subject), role=UserRole(claims.role))
    except ValueError as exc:
        raise AuthenticationError("Malformed token claims.") from exc
    # Surface the actor id to the logging middleware for correlation.
    request.state.actor_id = actor.id
    return actor


ActorDep = Annotated[CurrentActor, Depends(get_current_actor)]


def require_roles(*roles: UserRole) -> Callable[[CurrentActor], Awaitable[CurrentActor]]:
    async def _dependency(actor: ActorDep) -> CurrentActor:
        if actor.role not in roles:
            raise AuthorizationError("Your role may not perform this action.")
        return actor

    return _dependency


require_customer = require_roles(UserRole.CUSTOMER)
require_merchant = require_roles(UserRole.MERCHANT)
require_admin = require_roles(UserRole.ADMIN)

CustomerDep = Annotated[CurrentActor, Depends(require_customer)]
MerchantDep = Annotated[CurrentActor, Depends(require_merchant)]


def idempotency_key(
    key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    """Require and normalise the ``Idempotency-Key`` header."""
    if key is None or not key.strip():
        raise BadRequestError("The 'Idempotency-Key' header is required.")
    normalised = key.strip()
    if len(normalised) > 200:
        raise BadRequestError("The 'Idempotency-Key' header is too long (max 200).")
    return normalised


IdempotencyKeyDep = Annotated[str, Depends(idempotency_key)]
