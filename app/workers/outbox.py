"""Transactional-outbox worker entrypoint."""

from __future__ import annotations

from app.core.config import get_settings
from app.services.outbox_service import OutboxProcessor
from app.workers.runner import run_loop


async def run(*, run_once: bool = False) -> int:
    settings = get_settings()

    async def do_batch(session) -> int:  # type: ignore[no-untyped-def]
        result = await OutboxProcessor(session).run_batch(settings.outbox_batch_size)
        return result.processed + result.retried + result.failed

    return await run_loop(
        name="outbox",
        do_batch=do_batch,
        poll_interval=settings.worker_poll_interval_seconds,
        run_once=run_once,
    )
