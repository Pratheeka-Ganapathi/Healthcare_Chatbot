"""Use cases against in-memory fakes and a frozen clock (Tue 6 Oct 2026, 10:00 IST)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from clinic_bot.adapters.clock import FrozenClock
from clinic_bot.domain.day_resolver import DayResolver
from clinic_bot.domain.enums import AppointmentStatus, Sex, TimePref, VisitType
from clinic_bot.domain.errors import (
    BookingRejected,
    CutoffViolation,
    ErrorCode,
    InvalidInput,
    Locked,
    NotFound,
    NotOwner,
    SlotTaken,
)
from clinic_bot.domain.policies import (
    BookingPolicy,
    CancellationPolicy,
    FeePolicy,
    LockoutPolicy,
    SlotTimingPolicy,
)
from clinic_bot.services.booking import BookingService, CancelAppointment, ConfirmBooking
from clinic_bot.services.directory import DoctorDirectory
from clinic_bot.services.scheduling import SchedulingService
from clinic_bot.services.verification import VerificationService
from tests.fakes.data import seeded_memory
from tests.fakes.repos import InMemoryUnitOfWorkFactory

ASHA, RAHUL, MEENA, KIRAN, SANJAY = 1, 2, 3, 4, 5
RAO, RAO_S, NAIR, SHETTY = 1, 2, 3, 4


@pytest.fixture
async def uow(clock: FrozenClock) -> InMemoryUnitOfWorkFactory:
    return await seeded_memory(clock)


@pytest.fixture
async def directory(uow: InMemoryUnitOfWorkFactory) -> DoctorDirectory:
    d = DoctorDirectory(uow)
    await d.reload()
    return d


def booking(uow: InMemoryUnitOfWorkFactory, clock: FrozenClock) -> BookingService:
    return BookingService(uow, clock, BookingPolicy(), FeePolicy(), CancellationPolicy())


def scheduling(
    uow: InMemoryUnitOfWorkFactory, clock: FrozenClock, directory: DoctorDirectory
) -> SchedulingService:
    return SchedulingService(uow, clock, DayResolver(), SlotTimingPolicy(), directory)


# Verification -------------------------------------------------------------------------


async def test_verify_success(uow: InMemoryUnitOfWorkFactory, clock: FrozenClock) -> None:
    patient = await VerificationService(uow, clock, LockoutPolicy()).verify(
        "+91 90000 00005", "3 March 1995"
    )
    assert patient.name == "Sanjay Joshi"


async def test_wrong_phone_and_wrong_dob_fail_the_same_way(
    uow: InMemoryUnitOfWorkFactory, clock: FrozenClock
) -> None:
    service = VerificationService(uow, clock, LockoutPolicy())
    with pytest.raises(NotFound) as unknown_phone:
        await service.verify("9123456789", "03/03/1995")
    with pytest.raises(NotFound) as wrong_dob:
        await service.verify("9000000005", "04/03/1995")
    assert unknown_phone.value.code is wrong_dob.value.code is ErrorCode.NO_MATCH
    assert len(uow.store.attempts) == 2  # logged whether or not the phone exists


async def test_lockout_after_five_failures_across_sessions(
    uow: InMemoryUnitOfWorkFactory, clock: FrozenClock
) -> None:
    service = VerificationService(uow, clock, LockoutPolicy())
    for _ in range(5):
        with pytest.raises(NotFound):
            await service.verify("9000000005", "01/01/2000")
        clock.advance(timedelta(minutes=1))
    with pytest.raises(Locked):
        await service.verify("9000000005", "03/03/1995")  # even the right DOB
    clock.advance(timedelta(minutes=15))
    assert (await service.verify("9000000005", "03/03/1995")).id == SANJAY


async def test_unparseable_input_is_not_counted(
    uow: InMemoryUnitOfWorkFactory, clock: FrozenClock
) -> None:
    service = VerificationService(uow, clock, LockoutPolicy())
    with pytest.raises(InvalidInput):
        await service.verify("12345", "03/03/1995")
    assert uow.store.attempts == []


# Registration -------------------------------------------------------------------------


async def test_register_new_patient(uow: InMemoryUnitOfWorkFactory, clock: FrozenClock) -> None:
    service = VerificationService(uow, clock, LockoutPolicy())
    patient = await service.register(
        "  Priya  Sharma ", "+91 98888 00001", "12/04/1988", Sex.FEMALE
    )
    assert patient.name == "Priya Sharma" and patient.sex is Sex.FEMALE
    assert (await service.verify("9888800001", "12 April 1988")).id == patient.id
    assert service.age_of(patient) == 38


async def test_register_with_matching_existing_details_signs_in(
    uow: InMemoryUnitOfWorkFactory, clock: FrozenClock
) -> None:
    service = VerificationService(uow, clock, LockoutPolicy())
    patient = await service.register("sanjay joshi", "9000000005", "3 March 1995", Sex.MALE)
    assert patient.id == SANJAY
    assert len(uow.store.patients) == 6  # nothing new created


@pytest.mark.parametrize(
    ("name", "dob"), [("Sanjay Joshi", "04/03/1995"), ("Someone Else", "03/03/1995")]
)
async def test_register_over_an_existing_phone_fails_like_verification(
    uow: InMemoryUnitOfWorkFactory, clock: FrozenClock, name: str, dob: str
) -> None:
    service = VerificationService(uow, clock, LockoutPolicy())
    with pytest.raises(NotFound) as exc:
        await service.register(name, "9000000005", dob, Sex.MALE)
    assert exc.value.code is ErrorCode.NO_MATCH
    assert [a.success for a in uow.store.attempts] == [False]
    assert len(uow.store.patients) == 6


async def test_register_counts_toward_the_lockout(
    uow: InMemoryUnitOfWorkFactory, clock: FrozenClock
) -> None:
    service = VerificationService(uow, clock, LockoutPolicy())
    for _ in range(5):
        with pytest.raises(NotFound):
            await service.register("Not Sanjay", "9000000005", "03/03/1995", Sex.MALE)
    with pytest.raises(Locked):
        await service.verify("9000000005", "03/03/1995")


async def test_register_rejects_a_bad_name_without_writing(
    uow: InMemoryUnitOfWorkFactory, clock: FrozenClock
) -> None:
    service = VerificationService(uow, clock, LockoutPolicy())
    with pytest.raises(InvalidInput) as exc:
        await service.register("R2-D2", "9888800001", "12/04/1988", Sex.OTHER)
    assert exc.value.code is ErrorCode.BAD_NAME
    assert len(uow.store.patients) == 6 and uow.store.attempts == []


# Scheduling ---------------------------------------------------------------------------


async def test_free_slots_today_skip_the_next_30_minutes(
    uow: InMemoryUnitOfWorkFactory, clock: FrozenClock, directory: DoctorDirectory
) -> None:
    offer = await scheduling(uow, clock, directory).free_slots(RAO, "today", TimePref.MORNING)
    assert offer.slots and all(s.start >= clock.now() + timedelta(minutes=30) for s in offer.slots)
    assert len(offer.slots) <= 3 and offer.label == "Tue 6 Oct"


async def test_closed_day(
    uow: InMemoryUnitOfWorkFactory, clock: FrozenClock, directory: DoctorDirectory
) -> None:
    with pytest.raises(NotFound) as exc:
        await scheduling(uow, clock, directory).free_slots(RAO, "friday", TimePref.ANY)
    assert exc.value.code is ErrorCode.CLOSED
    assert "staff training" in str(exc.value.data["reason"])


async def test_no_slots_on_a_day_the_doctor_does_not_work(
    uow: InMemoryUnitOfWorkFactory, clock: FrozenClock, directory: DoctorDirectory
) -> None:
    with pytest.raises(NotFound) as exc:
        await scheduling(uow, clock, directory).free_slots(SHETTY, "thursday", TimePref.ANY)
    assert exc.value.code is ErrorCode.NO_SLOTS


async def test_alternatives(
    uow: InMemoryUnitOfWorkFactory, clock: FrozenClock, directory: DoctorDirectory
) -> None:
    offers = await scheduling(uow, clock, directory).alternatives(RAO_S, "thursday", TimePref.ANY)
    same_doctor = [o for o in offers if o.doctor_id == RAO_S]
    others = [o for o in offers if o.doctor_id != RAO_S]
    assert len(same_doctor) <= 2 and all(
        o.resolved_date.isoformat() > "2026-10-08" for o in same_doctor
    )
    assert {o.doctor_id for o in others} <= {RAO, NAIR}
    assert all(o.resolved_date.isoformat() == "2026-10-08" for o in others)


async def test_bad_day(
    uow: InMemoryUnitOfWorkFactory, clock: FrozenClock, directory: DoctorDirectory
) -> None:
    with pytest.raises(InvalidInput) as exc:
        await scheduling(uow, clock, directory).free_slots(RAO, "2026-11-30", TimePref.ANY)
    assert exc.value.code is ErrorCode.BAD_DAY


# Booking ------------------------------------------------------------------------------


async def _free_slot(
    uow: InMemoryUnitOfWorkFactory,
    clock: FrozenClock,
    directory: DoctorDirectory,
    doctor: int,
    day: str,
) -> int:
    offer = await scheduling(uow, clock, directory).free_slots(doctor, day, TimePref.ANY)
    return offer.slots[0].id


async def test_confirm_is_idempotent_per_session_and_slot(
    uow: InMemoryUnitOfWorkFactory, clock: FrozenClock, directory: DoctorDirectory
) -> None:
    slot_id = await _free_slot(uow, clock, directory, NAIR, "thursday")
    cmd = ConfirmBooking("s1", SANJAY, slot_id, None, None)
    first = await booking(uow, clock).confirm(cmd)
    second = await booking(uow, clock).confirm(cmd)
    assert first.id == second.id
    assert sum(1 for a, _ in uow.store.appointments.values() if a.patient_id == SANJAY) == 1


async def test_slot_taken_by_another_session(
    uow: InMemoryUnitOfWorkFactory, clock: FrozenClock, directory: DoctorDirectory
) -> None:
    slot_id = await _free_slot(uow, clock, directory, NAIR, "thursday")
    await booking(uow, clock).confirm(ConfirmBooking("s1", SANJAY, slot_id, None, None))
    with pytest.raises(SlotTaken):
        await booking(uow, clock).confirm(ConfirmBooking("s2", ASHA, slot_id, None, None))


async def test_cap_reached_for_third_upcoming(
    uow: InMemoryUnitOfWorkFactory, clock: FrozenClock, directory: DoctorDirectory
) -> None:
    service = booking(uow, clock)
    slot_id = await _free_slot(uow, clock, directory, SHETTY, "wednesday")
    await service.confirm(
        ConfirmBooking("s1", RAHUL, slot_id, None, None)
    )  # third upcoming: allowed
    another = await _free_slot(uow, clock, directory, NAIR, "saturday")
    with pytest.raises(BookingRejected) as exc:
        await service.confirm(ConfirmBooking("s1", RAHUL, another, None, None))
    assert exc.value.code is ErrorCode.CAP_REACHED


async def test_followup_fee_only_with_same_issue_and_grant_is_used(
    uow: InMemoryUnitOfWorkFactory, clock: FrozenClock, directory: DoctorDirectory
) -> None:
    service = booking(uow, clock)
    slot_id = await _free_slot(uow, clock, directory, RAO, "wednesday")
    quote_no = await service.quote(ASHA, slot_id, False)
    assert (quote_no.visit_type, quote_no.fee.paise) == (VisitType.NEW, 60000)
    appt = await service.confirm(ConfirmBooking("s1", ASHA, slot_id, None, True))
    assert (appt.visit_type, appt.fee.paise) == (VisitType.FOLLOWUP, 30000)
    assert await service.active_grant(ASHA, RAO) is None  # grant consumed
    assert appt.followup_grant_id is not None


async def test_cancel_rules(uow: InMemoryUnitOfWorkFactory, clock: FrozenClock) -> None:
    service = booking(uow, clock)
    [meena_soon] = await service.upcoming(MEENA)
    with pytest.raises(NotOwner):
        await service.cancel(CancelAppointment(ASHA, meena_soon.id or 0))
    with pytest.raises(CutoffViolation):
        await service.cancel(CancelAppointment(MEENA, meena_soon.id or 0))
    rahul_first = (await service.upcoming(RAHUL))[0]
    cancelled = await service.cancel(CancelAppointment(RAHUL, rahul_first.id or 0))
    assert cancelled.status is AppointmentStatus.CANCELLED
    assert len(await service.upcoming(RAHUL)) == 1
