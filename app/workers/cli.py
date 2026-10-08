"""Worker CLI: ``python -m app.workers.cli <worker> [--once]``.

Workers:
* ``expiry`` — release inventory from expired reservations.
* ``outbox`` — deliver transactional-outbox events.
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.config import get_settings
from app.core.runtime import configure_event_loop_policy
from app.observability.logging import configure_logging
from app.workers import expiry, outbox

_WORKERS = {
    "expiry": expiry.run,
    "outbox": outbox.run,
}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Background worker runner.")
    parser.add_argument("worker", choices=sorted(_WORKERS), help="Worker to run.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single batch and exit (useful for cron/tests).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    configure_event_loop_policy()
    args = _parse_args(argv)
    settings = get_settings()
    configure_logging(json_logs=settings.log_json, level=settings.log_level)
    runner = _WORKERS[args.worker]
    asyncio.run(runner(run_once=args.once))


if __name__ == "__main__":
    main()
