"""SQL repositories for the booking core: patients, doctors, slots, closures, appointments.

Records around bookings are in ``record_repositories``, staff data in ``staff_repositories``.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, delete, exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from clinic_bot.adapters.db import mappers
from clinic_bot.adapters.db.mappers import to_db_time
from clinic_bot.adapters.db.orm import (
    AppointmentRow,
    ClosureRow,
    DoctorRow,
    PatientRow,
    SlotRow,
)
from clinic_bot.domain.entities import (
    Appointment,
    Closure,
    Doctor,
    Patient,
    Slot,
)
from clinic_bot.domain.enums import AppointmentStatus, Sex, TimePref
from clinic_bot.domain.errors import Conflict, ErrorCode, NotFound, SlotTaken
from clinic_bot.domain.policies import SlotTimingPolicy
from clinic_bot.domain.values import DateOfBirth, PersonName, PhoneNumber
from clinic_bot.ports.clock import Clock

_BOOKED = AppointmentStatus.BOOKED.value


class SqlPatientRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def by_phone(self, phone: PhoneNumber) -> Patient | None:
        row = await self._s.scalar(select(PatientRow).where(PatientRow.phone == phone.digits))
        return mappers.patient(row) if row else None

    async def get(self, patient_id: int) -> Patient | None:
        row = await self._s.get(PatientRow, patient_id)
        return mappers.patient(row) if row else None

    async def many(self, patient_ids: Collection[int]) -> dict[int, Patient]:
        if not patient_ids:
            return {}
        rows = await self._s.scalars(select(PatientRow).where(PatientRow.id.in_(patient_ids)))
        return {r.id: mappers.patient(r) for r in rows}

    async def add(
        self, name: PersonName, phone: PhoneNumber, dob: DateOfBirth, sex: Sex, created_at: datetime
    ) -> Patient:
        row = PatientRow(
            name=name.value,
            phone=phone.digits,
            dob=dob.value,
            sex=sex.value,
            created_at=to_db_time(created_at),
        )
        self._s.add(row)
        try:
            await self._s.flush()
        except IntegrityError as exc:  # phone already registered
            raise NotFound(ErrorCode.NO_MATCH) from exc
        return mappers.patient(row)


class SqlDoctorRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def all(self) -> list[Doctor]:
        rows = await self._s.scalars(select(DoctorRow).order_by(DoctorRow.id))
        return [mappers.doctor(r) for r in rows]

    async def require(self, doctor_id: int) -> Doctor:
        row = await self._s.get(DoctorRow, doctor_id)
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND)
        return mappers.doctor(row)

    async def save(self, doctor: Doctor) -> None:
        row = await self._s.get(DoctorRow, doctor.id)
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND)
        row.name, row.bio = doctor.name, doctor.bio
        row.fee, row.followup_fee = doctor.fee.paise, doctor.followup_fee.paise
        await self._s.flush()


class SqlSlotRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def require(self, slot_id: int) -> Slot:
        row = await self._s.get(SlotRow, slot_id)
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND)
        return mappers.slot(row)

    async def free(
        self, doctor_id: int, day: date, time_pref: TimePref, not_before: datetime, limit: int
    ) -> list[Slot]:
        lo, hi = _pref_bounds(day, time_pref)
        lo = max(lo, to_db_time(not_before))
        booked = exists().where(
            and_(AppointmentRow.slot_id == SlotRow.id, AppointmentRow.status == _BOOKED)
        )
        stmt = (
            select(SlotRow)
            .where(SlotRow.doctor_id == doctor_id, SlotRow.start >= lo, SlotRow.start < hi, ~booked)
            .order_by(SlotRow.start)
            .limit(limit)
        )
        return [mappers.slot(r) for r in await self._s.scalars(stmt)]


def _pref_bounds(day: date, pref: TimePref) -> tuple[datetime, datetime]:
    start, end = (
        datetime.combine(day, time.min),
        datetime.combine(day + timedelta(days=1), time.min),
    )
    if pref is TimePref.MORNING:
        return start, datetime.combine(day, time(SlotTimingPolicy.MORNING_END_HOUR))
    if pref is TimePref.EVENING:
        return datetime.combine(day, time(SlotTimingPolicy.EVENING_START_HOUR)), end
    return start, end


class SqlClosureRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def on(self, day: date) -> Closure | None:
        row = await self._s.scalar(select(ClosureRow).where(ClosureRow.date == day))
        return Closure(row.date, row.reason, row.id) if row else None

    async def from_day(self, day: date) -> list[Closure]:
        stmt = select(ClosureRow).where(ClosureRow.date >= day).order_by(ClosureRow.date)
        return [Closure(r.date, r.reason, r.id) for r in await self._s.scalars(stmt)]

    async def add(self, closure: Closure) -> Closure:
        row = ClosureRow(date=closure.day, reason=closure.reason)
        self._s.add(row)
        try:
            await self._s.flush()
        except IntegrityError as exc:
            raise Conflict(ErrorCode.EXISTS) from exc
        return Closure(row.date, row.reason, row.id)

    async def delete(self, closure_id: int) -> None:
        result = await self._s.execute(delete(ClosureRow).where(ClosureRow.id == closure_id))
        if not result.rowcount:
            raise NotFound(ErrorCode.NOT_FOUND)


class SqlAppointmentRepo:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self._s, self._clock = session, clock

    def _select(self):  # type: ignore[no-untyped-def]
        return select(AppointmentRow, SlotRow).join(SlotRow, SlotRow.id == AppointmentRow.slot_id)

    async def get(self, appointment_id: int) -> Appointment | None:
        result = await self._s.execute(self._select().where(AppointmentRow.id == appointment_id))
        found = result.first()
        return mappers.appointment(found[0], found[1]) if found else None

    async def by_session_slot(self, session_id: str, slot_id: int) -> Appointment | None:
        stmt = self._select().where(
            AppointmentRow.session_id == session_id,
            AppointmentRow.slot_id == slot_id,
            AppointmentRow.status == _BOOKED,
        )
        found = (await self._s.execute(stmt)).first()
        return mappers.appointment(found[0], found[1]) if found else None

    async def upcoming_for_patient(self, patient_id: int, now: datetime) -> list[Appointment]:
        stmt = (
            self._select()
            .where(
                AppointmentRow.patient_id == patient_id,
                AppointmentRow.status == _BOOKED,
                SlotRow.start >= to_db_time(now),
            )
            .order_by(SlotRow.start)
        )
        return [mappers.appointment(a, s) for a, s in (await self._s.execute(stmt)).all()]

    async def add(self, appointment: Appointment, session_id: str) -> Appointment:
        row = AppointmentRow(
            patient_id=appointment.patient_id,
            doctor_id=appointment.doctor_id,
            slot_id=appointment.slot.id,
            visit_type=appointment.visit_type.value,
            fee=appointment.fee.paise,
            status=appointment.status.value,
            intake_summary=appointment.intake.to_dict() if appointment.intake else None,
            session_id=session_id,
            followup_grant_id=appointment.followup_grant_id,
            created_at=to_db_time(self._clock.now()),
        )
        self._s.add(row)
        try:
            await self._s.flush()
        except IntegrityError as exc:
            raise SlotTaken(ErrorCode.SLOT_TAKEN) from exc
        appointment.id = row.id
        return appointment

    async def save(self, appointment: Appointment) -> None:
        if appointment.id is None:
            raise NotFound(ErrorCode.NOT_FOUND)
        row = await self._s.get(AppointmentRow, appointment.id)
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND)
        row.status = appointment.status.value
        row.cancelled_at = (
            to_db_time(appointment.cancelled_at) if appointment.cancelled_at else None
        )
        row.intake_summary = appointment.intake.to_dict() if appointment.intake else None
        try:
            await self._s.flush()
        except IntegrityError as exc:
            raise SlotTaken(ErrorCode.SLOT_TAKEN) from exc

    async def between(
        self,
        start: datetime,
        end: datetime,
        *,
        doctor_id: int | None = None,
        newest_first: bool = False,
    ) -> list[Appointment]:
        stmt = self._select().where(
            SlotRow.start >= to_db_time(start), SlotRow.start < to_db_time(end)
        )
        if doctor_id is not None:
            stmt = stmt.where(AppointmentRow.doctor_id == doctor_id)
        order = SlotRow.start.desc() if newest_first else SlotRow.start
        rows = (await self._s.execute(stmt.order_by(order, AppointmentRow.id))).all()
        return [mappers.appointment(a, s) for a, s in rows]
