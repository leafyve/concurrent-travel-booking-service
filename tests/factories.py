"""Deterministic async factories for building test data.

Every factory commits so that concurrently-running requests (in concurrency
tests) can see the arranged state on their own connections.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.core.time import utcnow
from app.domain.enums import (
    CancellationPolicy,
    ExperienceStatus,
    MerchantStatus,
    SlotStatus,
    UserRole,
)
from app.models.experience import Experience, ExperienceSlot
from app.models.merchant import Merchant
from app.models.user import User

DEFAULT_PASSWORD = "correct horse battery staple"


async def create_user(
    session: AsyncSession,
    *,
    role: UserRole = UserRole.CUSTOMER,
    email: str | None = None,
    password: str = DEFAULT_PASSWORD,
    is_active: bool = True,
) -> User:
    user = User(
        email=email or f"{role.value}-{uuid.uuid4().hex[:8]}@example.test",
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
    )
    session.add(user)
    await session.commit()
    return user


async def create_merchant(session: AsyncSession, *, owner: User) -> Merchant:
    merchant = Merchant(
        owner_user_id=owner.id,
        display_name=f"Merchant {uuid.uuid4().hex[:6]}",
        status=MerchantStatus.ACTIVE,
    )
    session.add(merchant)
    await session.commit()
    return merchant


async def create_experience(
    session: AsyncSession,
    *,
    merchant: Merchant,
    destination: str = "Singapore",
    category: str = "cruise",
    currency: str = "SGD",
    base_price: Decimal = Decimal("80.00"),
    cancellation_policy: CancellationPolicy = (CancellationPolicy.FULLY_REFUNDABLE_UNTIL_24_HOURS),
) -> Experience:
    experience = Experience(
        merchant_id=merchant.id,
        title=f"Experience {uuid.uuid4().hex[:6]}",
        slug=f"exp-{uuid.uuid4().hex[:10]}",
        destination=destination,
        category=category,
        description="A fictional test experience.",
        status=ExperienceStatus.PUBLISHED,
        currency=currency,
        base_price=base_price,
        cancellation_policy=cancellation_policy,
    )
    session.add(experience)
    await session.commit()
    return experience


async def create_slot(
    session: AsyncSession,
    *,
    experience: Experience,
    capacity: int = 5,
    reserved: int = 0,
    confirmed: int = 0,
    starts_in_hours: float = 48.0,
    status: SlotStatus = SlotStatus.OPEN,
) -> ExperienceSlot:
    starts_at = utcnow() + timedelta(hours=starts_in_hours)
    slot = ExperienceSlot(
        experience_id=experience.id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=2),
        capacity=capacity,
        reserved_quantity=reserved,
        confirmed_quantity=confirmed,
        status=status,
    )
    session.add(slot)
    await session.commit()
    return slot


async def seed_customer_slot(
    session: AsyncSession,
    *,
    capacity: int = 5,
    base_price: Decimal = Decimal("80.00"),
    cancellation_policy: CancellationPolicy = (CancellationPolicy.FULLY_REFUNDABLE_UNTIL_24_HOURS),
) -> tuple[User, ExperienceSlot]:
    """Convenience: a customer plus a bookable slot behind a merchant."""
    owner = await create_user(session, role=UserRole.MERCHANT)
    customer = await create_user(session, role=UserRole.CUSTOMER)
    merchant = await create_merchant(session, owner=owner)
    experience = await create_experience(
        session,
        merchant=merchant,
        base_price=base_price,
        cancellation_policy=cancellation_policy,
    )
    slot = await create_slot(session, experience=experience, capacity=capacity)
    return customer, slot


def auth_header(user: User) -> dict[str, str]:
    token = create_access_token(subject=str(user.id), role=user.role.value)
    return {"Authorization": f"Bearer {token}"}
