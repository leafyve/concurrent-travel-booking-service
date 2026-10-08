"""Central application configuration.

All configuration is sourced from environment variables (12-factor style).
There are **no secrets committed to source control** — see ``.env.example`` for
the full set of variables with safe placeholder values.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- General -----------------------------------------------------------
    app_name: str = "Travel Booking Orchestration Service"
    environment: Literal["local", "test", "ci", "production"] = "local"
    debug: bool = False

    # --- Database ----------------------------------------------------------
    # A single psycopg3 URL powers both the async app engine and the sync
    # Alembic engine (SQLAlchemy selects the driver from the ``+psycopg`` tag).
    database_url: str = Field(
        default="postgresql+psycopg://booking:booking@localhost:5432/booking",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_pool_timeout_seconds: int = 30
    db_echo: bool = False

    # --- Authentication ----------------------------------------------------
    jwt_secret: str = Field(
        default="dev-only-insecure-change-me",
        description="HMAC signing secret for JWT access tokens.",
    )
    jwt_algorithm: str = "HS256"
    access_token_expires_minutes: int = 30

    # --- Reservations ------------------------------------------------------
    reservation_ttl_minutes: int = 10

    # --- Payment webhooks --------------------------------------------------
    webhook_signing_secret: str = Field(
        default="dev-only-webhook-secret-change-me",
        description="Shared HMAC secret used to sign/verify payment webhooks.",
    )
    webhook_replay_window_seconds: int = 300

    # --- Workers -----------------------------------------------------------
    expiry_batch_size: int = 100
    outbox_batch_size: int = 100
    outbox_max_attempts: int = 8
    worker_poll_interval_seconds: float = 2.0

    # --- Observability -----------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True

    @field_validator("database_url")
    @classmethod
    def _require_psycopg_driver(cls, value: str) -> str:
        """Ensure the URL uses the psycopg3 driver so async + sync both work."""
        scheme = value.split("://", 1)[0]
        if scheme not in {"postgresql+psycopg", "postgresql"}:
            raise ValueError(
                f"database_url must use the 'postgresql+psycopg' driver (got scheme '{scheme}')."
            )
        return value

    @property
    def async_database_url(self) -> str:
        """URL for the async SQLAlchemy engine (guaranteed +psycopg driver)."""
        raw = self.database_url
        if raw.startswith("postgresql+psycopg://"):
            return raw
        return raw.replace("postgresql://", "postgresql+psycopg://", 1)

    @property
    def sync_database_url(self) -> str:
        """URL for Alembic / synchronous access (same psycopg3 driver)."""
        return self.async_database_url


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()
