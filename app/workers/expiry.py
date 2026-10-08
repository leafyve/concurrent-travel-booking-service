"""Reservation-expiry worker entrypoint."""

from __future__ import annotations

from app.core.config import get_settings
from app.services.expiry_service import ReservationExpiryService
from app.workers.runner import run_loop


async def run(*, run_once: bool = False) -> int:
    settings = get_settings()

    async def do_batch(session) -> int:  # type: ignore[no-untyped-def]
        return await ReservationExpiryService(session).run_batch(settings.expiry_batch_size)

    return await run_loop(
        name="reservation_expiry",
        do_batch=do_batch,
        poll_interval=settings.worker_poll_interval_seconds,
        run_once=run_once,
    )
