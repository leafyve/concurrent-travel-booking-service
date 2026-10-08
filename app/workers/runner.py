"""Generic worker poll loop.

Creates a fresh session per batch, drains work greedily while there is any, and
sleeps ``poll_interval`` when idle. Handles SIGINT/SIGTERM for graceful
shutdown where the platform supports it (Linux containers).
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.observability.logging import get_logger

# A batch function processes one batch on the given session and returns how many
# units of work it handled (0 => idle).
BatchFn = Callable[[AsyncSession], Awaitable[int]]


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, ValueError):
            loop.add_signal_handler(sig, stop.set)


async def run_loop(
    *,
    name: str,
    do_batch: BatchFn,
    poll_interval: float,
    run_once: bool = False,
) -> int:
    """Run a worker loop. Returns the count handled by the final batch."""
    logger = get_logger(f"worker.{name}")
    maker = get_sessionmaker()
    stop = asyncio.Event()
    if not run_once:
        _install_signal_handlers(stop)

    logger.info("worker.start", worker=name, run_once=run_once)
    last = 0
    while not stop.is_set():
        async with maker() as session:
            last = await do_batch(session)
        if run_once:
            break
        if last == 0:
            # Idle: wait for the poll interval or an early shutdown signal.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=poll_interval)
    logger.info("worker.stop", worker=name)
    return last
