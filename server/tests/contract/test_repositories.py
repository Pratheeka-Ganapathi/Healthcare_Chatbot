"""One contract, two implementations: proves the in-memory fakes behave like PostgreSQL."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from clinic_bot.adapters.clock import FrozenClock
from clinic_bot.domain.entities import Appointment, Callback, ChatSummary, VerifyAttempt
from clinic_bot.domain.enums import AppointmentStatus, CallbackPriority, Sex, TimePref, VisitType
from clinic_bot.domain.errors import NotFound, SlotTaken
from clinic_bot.domain.values import DateOfBirth, Money, PersonName, PhoneNumber
from clinic_bot.ports.unit_of_work import UnitOfWorkFactory
from tests.fakes.data import seeded_memory, seeded_sql

WED = date(2026, 10, 7)


@pytest.fixture(params=["memory", "sql"])
async def uow(request: pytest.FixtureRequest, clock: FrozenClock) -> UnitOfWorkFactory:
    if request.param == "memory":
        return await seeded_memory(clock)
    return await seeded_sql(clock)


async def test_patients(uow: UnitOfWorkFactory) -> None:
    async with uow() as u:
        found = await u.patients.by_phone(PhoneNumber("9000000001"))
        assert found is not None and found.name == "Asha Kumar"
        assert await u.patients.by_phone(PhoneNumber("9999999999")) is None
        assert (await u.patients.get(found.id)) == found


async def test_add_patient(uow: UnitOfWorkFactory, clock: FrozenClock) -> None:
    name, dob = PersonName("Priya Sharma"), DateOfBirth(date(1988, 4, 12))
    async with uow(write=True) as u:
        added = await u.patients.add(name, PhoneNumber("9888800001"), dob, Sex.FEMALE, clock.now())
        await u.commit()
    async with uow() as u:
        assert await u.patients.by_phone(PhoneNumber("9888800001")) == added
    assert added.name == "Priya Sharma" and added.sex is Sex.FEMALE


async def test_add_patient_with_a_registered_phone_fails(
    uow: UnitOfWorkFactory, clock: FrozenClock
) -> None:
    name, dob = PersonName("Someone Else"), DateOfBirth(date(1990, 1, 1))
    async with uow(write=True) as u:
        with pytest.raises(NotFound):
            await u.patients.add(name, PhoneNumber("9000000001"), dob, Sex.MALE, clock.now())


async def test_doctors(uow: UnitOfWorkFactory) -> None:
    async with uow() as u:
        doctors = await u.doctors.all()
        assert len(doctors) == 8 and doctors[0].name == "Dr. Rao"
        with pytest.raises(NotFound):
            await u.doctors.require(999)


async def test_free_slots_filters(uow: UnitOfWorkFactory, clock: FrozenClock) -> None:
    async with uow() as u:
        morning = await u.slots.free(1, WED, TimePref.MORNING, clock.now(), 50)
        evening = await u.slots.free(1, WED, TimePref.EVENING, clock.now(), 50)
        limited = await u.slots.free(1, WED, TimePref.ANY, clock.now(), 3)
    assert morning and all(s.start.hour < 13 for s in morning)
    assert evening and all(s.start.hour >= 16 for s in evening)
    assert len(limited) == 3 and limited == sorted(limited, key=lambda s: s.start)


async def test_booking_round_trip(uow: UnitOfWorkFactory, clock: FrozenClock) -> None:
    async with uow(write=True) as u:
        [slot] = await u.slots.free(3, date(2026, 10, 8), TimePref.ANY, clock.now(), 1)
        appt = await u.appointments.add(
            Appointment.book(5, slot, VisitType.NEW, Money.rupees(500), None), "sess"
        )
        await u.commit()
    async with uow() as u:
        assert (await u.appointments.by_session_slot("sess", slot.id)) is not None
        assert slot not in await u.slots.free(3, date(2026, 10, 8), TimePref.ANY, clock.now(), 100)
        with pytest.raises(SlotTaken):
            await u.appointments.add(
                Appointment.book(1, slot, VisitType.NEW, Money.rupees(500), None), "other"
            )
    async with uow(write=True) as u:
        stored = await u.appointments.get(appt.id or 0)
        assert stored is not None and stored.status is AppointmentStatus.BOOKED
        stored.status = AppointmentStatus.CANCELLED
        stored.cancelled_at = clock.now()
        await u.appointments.save(stored)
        await u.commit()
    async with uow() as u:
        assert slot in await u.slots.free(3, date(2026, 10, 8), TimePref.ANY, clock.now(), 100)


async def test_uncommitted_work_is_rolled_back(uow: UnitOfWorkFactory, clock: FrozenClock) -> None:
    async with uow(write=True) as u:
        [slot] = await u.slots.free(3, date(2026, 10, 8), TimePref.ANY, clock.now(), 1)
        await u.appointments.add(
            Appointment.book(5, slot, VisitType.NEW, Money.rupees(500), None), "s"
        )
    async with uow() as u:
        assert await u.appointments.by_session_slot("s", slot.id) is None


async def test_upcoming_and_grants(uow: UnitOfWorkFactory, clock: FrozenClock) -> None:
    async with uow() as u:
        rahul = await u.appointments.upcoming_for_patient(2, clock.now())
        assert len(rahul) == 2 and rahul[0].slot.start < rahul[1].slot.start
        grant = await u.followups.active(1, 1, clock.today())
        assert grant is not None and grant.valid_until == clock.today() + timedelta(days=10)
        assert await u.followups.active(1, 2, clock.today()) is None
        assert await u.followups.active(1, 1, clock.today() + timedelta(days=11)) is None


async def test_attempts_and_callbacks(uow: UnitOfWorkFactory, clock: FrozenClock) -> None:
    async with uow(write=True) as u:
        await u.verify_attempts.add(VerifyAttempt("9000000005", clock.now(), False))
        saved = await u.callbacks.add(
            Callback(None, None, "help", "summary", CallbackPriority.HIGH, clock.now())
        )
        await u.commit()
    assert saved.ticket().startswith("CB-")
    async with uow() as u:
        recent = await u.verify_attempts.since("9000000005", clock.now() - timedelta(minutes=1))
        assert [a.success for a in recent] == [False]


async def test_rebook_a_cancelled_slot_in_the_same_session(
    uow: UnitOfWorkFactory, clock: FrozenClock
) -> None:
    async with uow(write=True) as u:
        [slot] = await u.slots.free(3, date(2026, 10, 8), TimePref.ANY, clock.now(), 1)
        appt = await u.appointments.add(
            Appointment.book(5, slot, VisitType.NEW, Money.rupees(500), None), "sess"
        )
        appt.status, appt.cancelled_at = AppointmentStatus.CANCELLED, clock.now()
        await u.appointments.save(appt)
        again = await u.appointments.add(
            Appointment.book(5, slot, VisitType.NEW, Money.rupees(500), None), "sess"
        )
        await u.commit()
    assert again.id != appt.id


async def test_chat_summaries(uow: UnitOfWorkFactory, clock: FrozenClock) -> None:
    first = ChatSummary(None, 5, "s1", "Booked dermatology.", clock.now())
    second = ChatSummary(None, 5, "s2", "Cancelled it.", clock.now() + timedelta(hours=2))
    async with uow(write=True) as u:
        saved = [await u.chat_summaries.add(s) for s in (first, second)]
        await u.chat_summaries.add(ChatSummary(None, 1, "s3", "Asked about hours.", clock.now()))
        await u.commit()
    assert all(s.id is not None for s in saved)
    async with uow() as u:
        assert await u.chat_summaries.for_patient(5) == saved[::-1]
        assert await u.chat_summaries.for_patient(2) == []
