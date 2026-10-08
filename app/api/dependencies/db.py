"""Database session dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session


async def _session_dep() -> AsyncIterator[AsyncSession]:
    async for session in get_db_session():
        yield session


SessionDep = Annotated[AsyncSession, Depends(_session_dep)]
