"""Locust load test for the booking API.

Measures throughput and latency of the read-heavy browse path plus the
write-heavy reservation path under concurrent virtual users.

Prerequisites: the API is running and the database is seeded
(``python -m scripts.seed``).

Run (headless example)::

    locust -f load_tests/locustfile.py --host http://127.0.0.1:8000 \
        --users 50 --spawn-rate 10 --run-time 30s --headless

Environment:
* ``LOAD_EMAIL`` / ``LOAD_PASSWORD`` — seeded customer credentials.
"""

from __future__ import annotations

import os
import uuid

from locust import HttpUser, between, task

EMAIL = os.environ.get("LOAD_EMAIL", "customer.alice@demo.test")
PASSWORD = os.environ.get("LOAD_PASSWORD", "Password123!")


class BookingUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
            name="POST /auth/login",
        )
        self.token = resp.json().get("access_token", "") if resp.ok else ""
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self._slot_ids: list[str] = self._discover_slots()

    def _discover_slots(self) -> list[str]:
        slot_ids: list[str] = []
        resp = self.client.get(
            "/api/v1/experiences",
            params={"min_available_capacity": 1},
            name="GET /experiences",
        )
        if not resp.ok:
            return slot_ids
        for experience in resp.json().get("items", [])[:3]:
            slots = self.client.get(
                f"/api/v1/experiences/{experience['id']}/slots",
                name="GET /experiences/{id}/slots",
            )
            if slots.ok:
                slot_ids.extend(s["id"] for s in slots.json())
        return slot_ids

    @task(6)
    def browse(self) -> None:
        self.client.get(
            "/api/v1/experiences",
            params={"destination": "Singapore"},
            name="GET /experiences?destination",
        )

    @task(3)
    def availability(self) -> None:
        if not self._slot_ids:
            return
        # Availability is served via the experience listing already discovered.
        self.client.get(
            "/api/v1/experiences",
            params={"min_available_capacity": 1},
            name="GET /experiences (availability)",
        )

    @task(2)
    def reserve(self) -> None:
        if not self.token or not self._slot_ids:
            return
        slot_id = self._slot_ids[0]
        self.client.post(
            "/api/v1/reservations",
            json={"slot_id": slot_id, "quantity": 1},
            headers={**self.headers, "Idempotency-Key": uuid.uuid4().hex},
            name="POST /reservations",
        )
