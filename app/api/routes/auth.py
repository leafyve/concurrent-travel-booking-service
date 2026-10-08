"""Authentication routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies.auth import ActorDep
from app.api.dependencies.db import SessionDep
from app.domain.errors import AuthenticationError
from app.repositories.user_repo import UserRepository
from app.schemas.auth import LoginRequest, TokenResponse, UserOut
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse, summary="Exchange credentials for a JWT")
async def login(payload: LoginRequest, session: SessionDep) -> TokenResponse:
    service = AuthService(session)
    user = await service.authenticate(str(payload.email), payload.password)
    return service.issue_token(user)


@router.get("/me", response_model=UserOut, summary="Current authenticated user")
async def me(actor: ActorDep, session: SessionDep) -> UserOut:
    user = await UserRepository(session).get_by_id(actor.id)
    if user is None:  # token valid but user removed
        raise AuthenticationError("User no longer exists.")
    return UserOut.model_validate(user)
