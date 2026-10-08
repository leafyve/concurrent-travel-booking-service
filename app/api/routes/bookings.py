"""Booking routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.dependencies.auth import ActorDep, CustomerDep, IdempotencyKeyDep
from app.api.dependencies.db import SessionDep
from app.schemas.booking import BookingCreate, BookingOut, CancellationOut
from app.services.booking_service import BookingService

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post(
    "",
    response_model=BookingOut,
    status_code=201,
    summary="Confirm a booking from a reservation (idempotent)",
)
async def create_booking(
    payload: BookingCreate,
    actor: CustomerDep,
    idempotency_key: IdempotencyKeyDep,
    session: SessionDep,
) -> JSONResponse:
    result = await BookingService(session).confirm(
        customer_id=actor.id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    return JSONResponse(
        status_code=result.status_code,
        content=result.body,
        headers={"Idempotent-Replayed": "true" if result.replayed else "false"},
    )


@router.get("/{booking_id}", response_model=BookingOut, summary="Get a booking")
async def get_booking(booking_id: uuid.UUID, actor: ActorDep, session: SessionDep) -> BookingOut:
    return await BookingService(session).get_booking(
        booking_id=booking_id, actor_id=actor.id, actor_role=actor.role
    )


@router.post(
    "/{booking_id}/cancel",
    response_model=CancellationOut,
    summary="Cancel a booking (idempotent, restores inventory once)",
)
async def cancel_booking(
    booking_id: uuid.UUID, actor: ActorDep, session: SessionDep
) -> CancellationOut:
    return await BookingService(session).cancel(
        booking_id=booking_id, actor_id=actor.id, actor_role=actor.role
    )
