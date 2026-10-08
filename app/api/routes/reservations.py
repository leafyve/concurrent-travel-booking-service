"""Reservation routes."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.dependencies.auth import CustomerDep, IdempotencyKeyDep
from app.api.dependencies.db import SessionDep
from app.schemas.reservation import ReservationCreate, ReservationOut
from app.services.reservation_service import ReservationService

router = APIRouter(prefix="/reservations", tags=["reservations"])


@router.post(
    "",
    response_model=ReservationOut,
    status_code=201,
    summary="Create an inventory reservation (idempotent)",
)
async def create_reservation(
    payload: ReservationCreate,
    actor: CustomerDep,
    idempotency_key: IdempotencyKeyDep,
    session: SessionDep,
) -> JSONResponse:
    result = await ReservationService(session).create(
        customer_id=actor.id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    return JSONResponse(
        status_code=result.status_code,
        content=result.body,
        headers={"Idempotent-Replayed": "true" if result.replayed else "false"},
    )
