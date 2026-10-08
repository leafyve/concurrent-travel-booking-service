"""Experience search and availability routes (public read side)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies.db import SessionDep
from app.repositories.experience_repo import ExperienceSearchFilters
from app.schemas.common import Page
from app.schemas.experience import (
    ExperienceDetail,
    ExperienceListItem,
    SlotAvailability,
)
from app.services.experience_service import ExperienceService

router = APIRouter(prefix="/experiences", tags=["experiences"])


@router.get("", response_model=Page[ExperienceListItem], summary="Search experiences")
async def search_experiences(
    session: SessionDep,
    destination: Annotated[str | None, Query(max_length=120)] = None,
    category: Annotated[str | None, Query(max_length=80)] = None,
    starts_from: Annotated[datetime | None, Query()] = None,
    starts_to: Annotated[datetime | None, Query()] = None,
    min_available_capacity: Annotated[int, Query(ge=0, le=1000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ExperienceListItem]:
    filters = ExperienceSearchFilters(
        destination=destination,
        category=category,
        starts_from=starts_from,
        starts_to=starts_to,
        min_available_capacity=min_available_capacity,
        limit=limit,
        offset=offset,
    )
    return await ExperienceService(session).search(filters)


@router.get(
    "/{experience_id}",
    response_model=ExperienceDetail,
    summary="Get one experience",
)
async def get_experience(experience_id: uuid.UUID, session: SessionDep) -> ExperienceDetail:
    return await ExperienceService(session).get_detail(experience_id)


@router.get(
    "/{experience_id}/slots",
    response_model=list[SlotAvailability],
    summary="List bookable slots with live availability",
)
async def list_slots(
    experience_id: uuid.UUID,
    session: SessionDep,
    starts_from: Annotated[datetime | None, Query()] = None,
    starts_to: Annotated[datetime | None, Query()] = None,
) -> list[SlotAvailability]:
    return await ExperienceService(session).list_availability(
        experience_id, starts_from=starts_from, starts_to=starts_to
    )
