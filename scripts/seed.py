"""Seed fictional demonstration data.

Idempotent: re-running detects the seeded admin and exits without duplicating.
All data is fictional. Credentials below are for **local demonstration only** and
must never be reused anywhere real.

Run: ``python -m scripts.seed``
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.core.security import hash_password
from app.core.time import utcnow
from app.db.session import dispose_engine, session_scope
from app.domain.enums import (
    BookingStatus,
    CancellationPolicy,
    MerchantStatus,
    ReservationStatus,
    UserRole,
)
from app.domain.references import generate_booking_reference
from app.models.booking import Booking
from app.models.experience import Experience, ExperienceSlot
from app.models.merchant import Merchant
from app.models.reservation import Reservation
from app.models.user import User

DEMO_PASSWORD = "Password123!"

ACCOUNTS = [
    ("admin@demo.test", UserRole.ADMIN),
    ("merchant.marina@demo.test", UserRole.MERCHANT),
    ("merchant.eastasia@demo.test", UserRole.MERCHANT),
    ("customer.alice@demo.test", UserRole.CUSTOMER),
    ("customer.ben@demo.test", UserRole.CUSTOMER),
]

# (title, slug, destination, category, currency, base_price, policy, merchant_key)
EXPERIENCES = [
    (
        "Marina Night River Cruise",
        "marina-night-river-cruise",
        "Singapore",
        "cruise",
        "SGD",
        Decimal("68.00"),
        CancellationPolicy.FULLY_REFUNDABLE_UNTIL_24_HOURS,
        "marina",
    ),
    (
        "Sentosa Sunset Kayak Tour",
        "sentosa-sunset-kayak-tour",
        "Singapore",
        "adventure",
        "SGD",
        Decimal("95.00"),
        CancellationPolicy.FLEXIBLE_UNTIL_START,
        "marina",
    ),
    (
        "Shinjuku Food Discovery Walk",
        "shinjuku-food-discovery-walk",
        "Tokyo",
        "food",
        "JPY",
        Decimal("9800"),
        CancellationPolicy.NON_REFUNDABLE,
        "eastasia",
    ),
    (
        "Seoul Palace and Market Tour",
        "seoul-palace-and-market-tour",
        "Seoul",
        "culture",
        "KRW",
        Decimal("72000"),
        CancellationPolicy.FULLY_REFUNDABLE_UNTIL_24_HOURS,
        "eastasia",
    ),
    (
        "Bangkok Canal Morning Experience",
        "bangkok-canal-morning-experience",
        "Bangkok",
        "cruise",
        "THB",
        Decimal("1500.00"),
        CancellationPolicy.FLEXIBLE_UNTIL_START,
        "eastasia",
    ),
]


async def _already_seeded(session) -> bool:  # type: ignore[no-untyped-def]
    existing = await session.scalar(
        select(func.count()).select_from(User).where(User.email == "admin@demo.test")
    )
    return bool(existing)


async def seed() -> None:
    async with session_scope() as session:
        if await _already_seeded(session):
            print("Seed data already present — nothing to do.")
            return

        users: dict[str, User] = {}
        for email, role in ACCOUNTS:
            user = User(
                email=email,
                password_hash=hash_password(DEMO_PASSWORD),
                role=role,
                is_active=True,
            )
            session.add(user)
            users[email] = user
        await session.flush()

        merchants = {
            "marina": Merchant(
                owner_user_id=users["merchant.marina@demo.test"].id,
                display_name="Marina Bay Experiences Co. (fictional)",
                status=MerchantStatus.ACTIVE,
            ),
            "eastasia": Merchant(
                owner_user_id=users["merchant.eastasia@demo.test"].id,
                display_name="East Asia Trails (fictional)",
                status=MerchantStatus.ACTIVE,
            ),
        }
        session.add_all(merchants.values())
        await session.flush()

        first_slot: ExperienceSlot | None = None
        for (
            title,
            slug,
            destination,
            category,
            currency,
            price,
            policy,
            merchant_key,
        ) in EXPERIENCES:
            experience = Experience(
                merchant_id=merchants[merchant_key].id,
                title=title,
                slug=slug,
                destination=destination,
                category=category,
                description=f"A fictional {category} experience in {destination}.",
                currency=currency,
                base_price=price,
                cancellation_policy=policy,
            )
            session.add(experience)
            await session.flush()

            for day in (1, 2, 3):
                for hour, capacity in ((10, 12), (15, 6), (19, 4)):
                    starts_at = (utcnow() + timedelta(days=day)).replace(
                        hour=hour, minute=0, second=0, microsecond=0
                    )
                    slot = ExperienceSlot(
                        experience_id=experience.id,
                        starts_at=starts_at,
                        ends_at=starts_at + timedelta(hours=2),
                        capacity=capacity,
                    )
                    session.add(slot)
                    if first_slot is None:
                        await session.flush()
                        first_slot = slot

        # A couple of example bookings on the very first slot.
        assert first_slot is not None
        alice = users["customer.alice@demo.test"]
        await _seed_example_booking(session, customer=alice, slot=first_slot, confirmed=True)
        await _seed_example_booking(
            session,
            customer=users["customer.ben@demo.test"],
            slot=first_slot,
            confirmed=False,
        )

    await dispose_engine()
    print("Seeded fictional data successfully.")
    print(f"Demo accounts (password '{DEMO_PASSWORD}'):")
    for email, role in ACCOUNTS:
        print(f"  - {email:32} [{role.value}]")


async def _seed_example_booking(session, *, customer, slot, confirmed) -> None:  # type: ignore[no-untyped-def]
    experience = await session.get(Experience, slot.experience_id)
    assert experience is not None
    unit_price = experience.base_price
    total = unit_price  # quantity 1
    reservation = Reservation(
        customer_id=customer.id,
        slot_id=slot.id,
        quantity=1,
        unit_price=unit_price,
        total_price=total,
        currency=experience.currency,
        status=ReservationStatus.CONVERTED,
        expires_at=utcnow() + timedelta(minutes=10),
    )
    session.add(reservation)
    await session.flush()
    slot.confirmed_quantity += 1
    booking = Booking(
        booking_reference=generate_booking_reference(),
        reservation_id=reservation.id,
        customer_id=customer.id,
        slot_id=slot.id,
        quantity=1,
        total_price=total,
        currency=experience.currency,
        status=BookingStatus.CONFIRMED if confirmed else BookingStatus.PENDING_PAYMENT,
    )
    session.add(booking)


def main() -> None:
    from app.core.runtime import configure_event_loop_policy

    configure_event_loop_policy()
    asyncio.run(seed())


if __name__ == "__main__":
    main()
