"""Prometheus metrics.

Business counters live here as module-level singletons so services can increment
them without importing FastAPI. The ``/metrics`` route renders the default
registry in Prometheus text format.
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# --- HTTP-level -----------------------------------------------------------
HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests.",
    labelnames=("method", "route", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    labelnames=("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# --- Business domain ------------------------------------------------------
RESERVATIONS_CREATED = Counter("reservations_created_total", "Active reservations created.")
RESERVATIONS_EXPIRED = Counter("reservations_expired_total", "Reservations expired by the worker.")
BOOKINGS_CONFIRMED = Counter("bookings_confirmed_total", "Bookings confirmed.")
BOOKINGS_CANCELLED = Counter("bookings_cancelled_total", "Bookings cancelled.")
INVENTORY_CONFLICTS = Counter(
    "inventory_conflicts_total", "Reservation attempts rejected for lack of capacity."
)
WEBHOOK_REJECTIONS = Counter(
    "webhook_rejections_total",
    "Rejected payment webhooks.",
    labelnames=("reason",),
)
OUTBOX_RETRIES = Counter(
    "outbox_retries_total", "Outbox delivery attempts that failed and will retry."
)

# --- Workers --------------------------------------------------------------
WORKER_BATCH_DURATION = Histogram(
    "worker_batch_duration_seconds",
    "Duration of a single worker batch.",
    labelnames=("worker",),
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
)


def render_latest() -> tuple[bytes, str]:
    """Return (payload, content_type) for the /metrics endpoint."""
    return generate_latest(), CONTENT_TYPE_LATEST
