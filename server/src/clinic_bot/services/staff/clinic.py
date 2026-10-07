"""Admin: overview counts, doctor profiles and fees, closure days (SPEC 17.3)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta

from clinic_bot.domain.entities import Closure, Doctor
from clinic_bot.domain.enums import AppointmentStatus
from clinic_bot.domain.errors import ErrorCode, InvalidInput
from clinic_bot.domain.staff import StaffUser, check_staff_name
from clinic_bot.domain.values import Money
from clinic_bot.ports.clock import Clock
from clinic_bot.ports.staff import TableBrowser
from clinic_bot.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from clinic_bot.services.directory import DoctorDirectory

MAX_BIO = 1000
MAX_FEE_RUPEES = 100_000
MAX_REASON = 200
COUNTED_TABLES = ("patients", "doctors", "consultations", "chat_summaries", "callbacks")


@dataclass(frozen=True, slots=True)
class Overview:
    counts: dict[str, int]
    appointments_today: int
    upcoming_appointments: int


@dataclass(frozen=True, slots=True)
class DoctorAccount:
    doctor: Doctor
    account: StaffUser | None


@dataclass(frozen=True, slots=True)
class ClosureDay:
    closure: Closure
    booked_appointments: int


def _fee(rupees: int) -> Money:
    if not 0 <= rupees <= MAX_FEE_RUPEES:
        raise InvalidInput(ErrorCode.INVALID, "fee out of range")
    return Money.rupees(rupees)


class ClinicAdminService:
    def __init__(
        self,
        uow: UnitOfWorkFactory,
        clock: Clock,
        directory: DoctorDirectory,
        tables: TableBrowser,
    ) -> None:
        self._uow, self._clock, self._directory, self._tables = uow, clock, directory, tables

    async def overview(self) -> Overview:
        now = self._clock.now()
        counts = await self._tables.counts(COUNTED_TABLES)
        async with self._uow() as uow:
            today = await uow.appointments.between(
                self._at(now.date()), self._at(now.date() + timedelta(days=1))
            )
            ahead = await uow.appointments.between(now, now + timedelta(days=366))
        live = [a for a in today if a.status is not AppointmentStatus.CANCELLED]
        upcoming = [a for a in ahead if a.status is AppointmentStatus.BOOKED]
        return Overview(counts, len(live), len(upcoming))

    async def doctors(self) -> list[DoctorAccount]:
        async with self._uow() as uow:
            doctors = await uow.doctors.all()
            accounts = {u.doctor_id: u for u in await uow.staff_users.all() if u.doctor_id}
        return [DoctorAccount(d, accounts.get(d.id)) for d in doctors]

    async def update_doctor(
        self, doctor_id: int, *, name: str, bio: str, fee_rupees: int, followup_fee_rupees: int
    ) -> DoctorAccount:
        """Raises ``NotFound``, ``InvalidInput``. The chatbot's directory reloads."""
        if len(bio) > MAX_BIO:
            raise InvalidInput(ErrorCode.INVALID, "bio too long")
        async with self._uow(write=True) as uow:
            doctor = replace(
                await uow.doctors.require(doctor_id),
                name=check_staff_name(name),
                bio=bio.strip(),
                fee=_fee(fee_rupees),
                followup_fee=_fee(followup_fee_rupees),
            )
            await uow.doctors.save(doctor)
            account = await uow.staff_users.by_doctor(doctor_id)
            await uow.commit()
        await self._directory.reload()
        return DoctorAccount(doctor, account)

    async def closures(self) -> list[ClosureDay]:
        async with self._uow() as uow:
            closures = await uow.closures.from_day(self._clock.today())
            return [ClosureDay(c, await self._booked_on(uow, c.day)) for c in closures]

    async def add_closure(self, day: date, reason: str) -> ClosureDay:
        """Existing bookings on the day are kept. Raises ``InvalidInput(PAST_DAY)``,
        ``Conflict(EXISTS)``."""
        if day < self._clock.today():
            raise InvalidInput(ErrorCode.PAST_DAY)
        text = " ".join(reason.split())
        if not 1 <= len(text) <= MAX_REASON:
            raise InvalidInput(ErrorCode.INVALID, "reason needs 1 to 200 characters")
        async with self._uow(write=True) as uow:
            closure = await uow.closures.add(Closure(day, text))
            booked = await self._booked_on(uow, day)
            await uow.commit()
        return ClosureDay(closure, booked)

    async def delete_closure(self, closure_id: int) -> None:
        """Raises ``NotFound``."""
        async with self._uow(write=True) as uow:
            await uow.closures.delete(closure_id)
            await uow.commit()

    async def _booked_on(self, uow: UnitOfWork, day: date) -> int:
        appts = await uow.appointments.between(self._at(day), self._at(day + timedelta(days=1)))
        return sum(a.status is AppointmentStatus.BOOKED for a in appts)

    def _at(self, day: date) -> datetime:
        return datetime.combine(day, time.min, tzinfo=self._clock.now().tzinfo)
