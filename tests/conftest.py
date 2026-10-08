"""Shared pytest fixtures and the real-PostgreSQL test harness.

The suite runs against a **real PostgreSQL** database (never SQLite) so that
constraints, row locks, and ``FOR UPDATE SKIP LOCKED`` behave exactly as in
production. Each test gets a clean set of tables (truncation) and a fresh async
engine bound to a per-session throwaway database.

On Windows, psycopg's async mode requires a SelectorEventLoop, so we install the
selector policy before anything else. Production runs on Linux where the default
loop is already compatible.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from collections.abc import AsyncIterator, Iterator

# --- Windows event-loop compatibility (must run before asyncio is used) ------
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# --- Test environment (must be set before importing the app/settings) --------
_ADMIN_URL = os.environ.get(
    "TEST_ADMIN_DATABASE_URL",
    "postgresql+psycopg://booking:booking@127.0.0.1:55432/booking",
)
_TEST_DB_NAME = f"booking_test_{uuid.uuid4().hex[:10]}"
_TEST_URL = _ADMIN_URL.rsplit("/", 1)[0] + f"/{_TEST_DB_NAME}"

os.environ["DATABASE_URL"] = _TEST_URL
os.environ["JWT_SECRET"] = "test-jwt-secret-0123456789abcdef0123456789abcdef"
os.environ["WEBHOOK_SIGNING_SECRET"] = "test-webhook-secret"
os.environ["WEBHOOK_REPLAY_WINDOW_SECONDS"] = "300"
os.environ["RESERVATION_TTL_MINUTES"] = "10"
os.environ["LOG_JSON"] = "false"
os.environ["ENVIRONMENT"] = "test"

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.models  # noqa: E402,F401  (register metadata)
from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402

get_settings.cache_clear()

_SYNC_ADMIN = _ADMIN_URL  # psycopg sync + async share the URL form
_SYNC_TEST = _TEST_URL


def _admin_execute(sql: str) -> None:
    engine = create_engine(_SYNC_ADMIN, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(sql))
    finally:
        engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    """Create a throwaway test database + schema for the whole session."""
    _admin_execute(f'CREATE DATABASE "{_TEST_DB_NAME}"')
    sync_engine = create_engine(_SYNC_TEST)
    try:
        Base.metadata.create_all(sync_engine)
    finally:
        sync_engine.dispose()
    try:
        yield
    finally:
        # Terminate stray connections, then drop the database.
        _admin_execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{_TEST_DB_NAME}' AND pid <> pg_backend_pid()"
        )
        _admin_execute(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}"')


@pytest.fixture(autouse=True)
def _clean_tables() -> Iterator[None]:
    """Truncate all tables before each test for isolation."""
    tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    sync_engine = create_engine(_SYNC_TEST, isolation_level="AUTOCOMMIT")
    try:
        with sync_engine.connect() as conn:
            conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    finally:
        sync_engine.dispose()
    yield


@pytest.fixture
async def engine() -> AsyncIterator[object]:
    """A fresh async engine per test (avoids cross-event-loop pool reuse)."""
    eng = create_async_engine(
        _TEST_URL,
        pool_size=30,
        max_overflow=20,
        pool_pre_ping=True,
    )
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture
def sessionmaker_(engine: object) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,  # type: ignore[arg-type]
        expire_on_commit=False,
        autoflush=False,
    )


@pytest.fixture
async def db_session(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with sessionmaker_() as session:
        yield session


@pytest.fixture
async def client(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> AsyncIterator[object]:
    """An httpx AsyncClient wired to the app, using the test engine."""
    import httpx

    from app.api.dependencies.db import _session_dep
    from app.main import app

    async def _override() -> AsyncIterator[AsyncSession]:
        async with sessionmaker_() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[_session_dep] = _override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    app.dependency_overrides.clear()
