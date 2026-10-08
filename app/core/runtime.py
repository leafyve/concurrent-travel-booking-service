"""Runtime/event-loop compatibility helpers.

psycopg's async mode requires a ``SelectorEventLoop``. On Linux (the deployment
target) that is already the default, so this is a no-op. On Windows the default
is ``ProactorEventLoop``, so local entrypoints call
:func:`configure_event_loop_policy` before ``asyncio.run`` to switch policies.
"""

from __future__ import annotations

import asyncio
import sys


def configure_event_loop_policy() -> None:
    """Install a psycopg-compatible event loop policy on Windows."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
