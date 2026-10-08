"""Local API runner.

Runs uvicorn on an explicitly-created event loop so the psycopg-compatible
selector policy (needed on Windows) is honoured. In Docker/Linux the default
loop already works, but this entrypoint is safe everywhere:
``python -m scripts.run_api``.
"""

from __future__ import annotations

import asyncio
import os

import uvicorn

from app.core.runtime import configure_event_loop_policy


async def _serve() -> None:
    config = uvicorn.Config(
        "app.main:app",
        host=os.environ.get("API_HOST", "127.0.0.1"),
        port=int(os.environ.get("API_PORT", "8000")),
        log_config=None,
    )
    server = uvicorn.Server(config)
    await server.serve()


def main() -> None:
    # asyncio.run() creates the loop via the (now selector) policy on Windows.
    configure_event_loop_policy()
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
