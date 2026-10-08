"""Standalone worker processes that share the app's codebase and database.

Two workers back the durable background work:

* ``reservation_expiry`` — releases inventory from expired holds.
* ``outbox`` — delivers transactional-outbox events to consumers.

They run as separate processes (``python -m app.workers.cli <name>``) so they
scale and fail independently of the API. A DB-backed design (locking + batches)
replaces any in-process timer.
"""
