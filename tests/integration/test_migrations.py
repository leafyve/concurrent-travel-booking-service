"""Integration test: Alembic migrations apply and revert on an empty database."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ADMIN_URL = os.environ.get(
    "TEST_ADMIN_DATABASE_URL",
    "postgresql+psycopg://booking:booking@127.0.0.1:55432/booking",
)
_BASE = _ADMIN_URL.rsplit("/", 1)[0]


def _admin_exec(sql: str) -> None:
    engine = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(sql))
    finally:
        engine.dispose()


def _alembic(db_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_migrations_upgrade_and_downgrade() -> None:
    db_name = f"booking_mig_{uuid.uuid4().hex[:10]}"
    db_url = f"{_BASE}/{db_name}"
    _admin_exec(f'CREATE DATABASE "{db_name}"')
    try:
        up = _alembic(db_url, "upgrade", "head")
        assert up.returncode == 0, up.stderr

        engine = create_engine(db_url)
        try:
            tables = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        assert {
            "users",
            "experiences",
            "experience_slots",
            "reservations",
            "bookings",
            "payment_attempts",
            "outbox_events",
        } <= tables

        down = _alembic(db_url, "downgrade", "base")
        assert down.returncode == 0, down.stderr

        engine = create_engine(db_url)
        try:
            remaining = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        # Everything except Alembic's own bookkeeping table is gone.
        assert "users" not in remaining
        assert "bookings" not in remaining
    finally:
        _admin_exec(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"
        )
        _admin_exec(f'DROP DATABASE IF EXISTS "{db_name}"')
