"""Authentication service: credential verification and token issuance."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.domain.errors import AuthenticationError
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import TokenResponse


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._users = UserRepository(session)

    async def authenticate(self, email: str, password: str) -> User:
        user = await self._users.get_by_email(email)
        # Verify a hash even when the user is missing to reduce timing signal,
        # then return a single generic error (no user-enumeration).
        candidate_hash = user.password_hash if user else _DUMMY_HASH
        # bcrypt is deliberately CPU-heavy; run it in a worker thread so it does
        # not block the event loop (and stall unrelated requests) under load.
        password_ok = await asyncio.to_thread(verify_password, password, candidate_hash)
        if user is None or not password_ok or not user.is_active:
            raise AuthenticationError("Invalid email or password.")
        return user

    def issue_token(self, user: User) -> TokenResponse:
        settings = get_settings()
        token = create_access_token(subject=str(user.id), role=user.role.value)
        return TokenResponse(
            access_token=token,
            expires_in=settings.access_token_expires_minutes * 60,
        )


# A valid bcrypt hash of a fixed random string, used only to equalise timing on
# the "user not found" path. It can never match a real password.
_DUMMY_HASH = hash_password("not-a-real-password-timing-guard")
