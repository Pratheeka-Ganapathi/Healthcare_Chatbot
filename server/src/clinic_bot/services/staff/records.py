"""Appointment lists and the appointment page for doctors and admins (SPEC 17.2, 17.3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal

from clinic_bot.domain.entities import Appointment, ChatSummary, Doctor, Patient
from clinic_bot.domain.enums import AppointmentStatus
from clinic_bot.domain.errors import ErrorCode, NotFound
from clinic_bot.domain.staff import Consultation
from clinic_bot.ports.clock import Clock
from clinic_bot.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from clinic_bot.services.directory import DoctorDirectory

Scope = Literal["today", "upcoming", "past"]
PAST_DAYS = 90
UPCOMING_DAYS = 60


@dataclass(frozen=True, slots=True)
class Visit:
    """One appointment with the people it involves."""

    appointment: Appointment
    patient: Patient
    patient_age: int
    doctor: Doctor
    has_consultation: bool


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    appointment_id: int
    day: date
    doctor_name: str
    consultation: Consultation


@dataclass(frozen=True, slots=True)
class VisitRecord:
    visit: Visit
    consultation: Consultation | None
    consultation_by: str | None
    followup_valid_until: date | None
    chat_summaries: tuple[ChatSummary, ...]
    history: tuple[HistoryEntry, ...]
    can_record: bool


async def owned_appointment(
    uow: UnitOfWork, appointment_id: int, doctor_id: int | None
) -> Appointment:
    """``doctor_id`` None means an admin. Someone else's appointment is ``NotFound``."""
    appt = await uow.appointments.get(appointment_id)
    if appt is None or (doctor_id is not None and appt.doctor_id != doctor_id):
        raise NotFound(ErrorCode.NOT_FOUND)
    return appt


class VisitRecords:
    def __init__(self, uow: UnitOfWorkFactory, clock: Clock, directory: DoctorDirectory) -> None:
        self._uow, self._clock, self._directory = uow, clock, directory

    async def for_doctor(self, doctor_id: int, scope: Scope) -> list[Visit]:
        today = self._clock.today()
        if scope == "today":
            start, end, newest = today, today + timedelta(days=1), False
        elif scope == "upcoming":
            start, end, newest = today + timedelta(days=1), today + timedelta(UPCOMING_DAYS), False
        else:
            start, end, newest = today - timedelta(days=PAST_DAYS), today, True
        return await self._visits(start, end, doctor_id, newest)

    async def on_day(self, day: date) -> list[Visit]:
        return await self._visits(day, day + timedelta(days=1), None, False)

    async def record(self, appointment_id: int, doctor_id: int | None) -> VisitRecord:
        """The appointment page. Raises ``NotFound``."""
        async with self._uow() as uow:
            appt = await owned_appointment(uow, appointment_id, doctor_id)
            consultation = await uow.consultations.for_appointment(appointment_id)
            by = await uow.staff_users.get(consultation.submitted_by) if consultation else None
            grant_id = consultation.followup_grant_id if consultation else None
            grant = await uow.followups.get(grant_id) if grant_id else None
            [visit] = await self._enrich(uow, [appt])
            summaries = await uow.chat_summaries.for_patient(appt.patient_id)
            history = await self._history(uow, appt)
        today = self._clock.today()
        return VisitRecord(
            visit=visit,
            consultation=consultation,
            consultation_by=by.name if by else None,
            followup_valid_until=grant.valid_until if grant else None,
            chat_summaries=tuple(summaries),
            history=history,
            can_record=appt.status is not AppointmentStatus.CANCELLED and appt.slot.day <= today,
        )

    async def _visits(
        self, start: date, end: date, doctor_id: int | None, newest_first: bool
    ) -> list[Visit]:
        async with self._uow() as uow:
            appts = await uow.appointments.between(
                self._at(start), self._at(end), doctor_id=doctor_id, newest_first=newest_first
            )
            return await self._enrich(uow, appts)

    async def _enrich(self, uow: UnitOfWork, appts: list[Appointment]) -> list[Visit]:
        patients = await uow.patients.many({a.patient_id for a in appts})
        done = await uow.consultations.with_consultation({a.id for a in appts if a.id})
        today = self._clock.today()
        return [
            Visit(
                appointment=a,
                patient=patients[a.patient_id],
                patient_age=patients[a.patient_id].age_on(today),
                doctor=self._directory.get(a.doctor_id),
                has_consultation=a.id in done,
            )
            for a in appts
        ]

    async def _history(self, uow: UnitOfWork, appt: Appointment) -> tuple[HistoryEntry, ...]:
        """The patient's other consultations, with any doctor, newest first."""
        entries: list[HistoryEntry] = []
        for c in await uow.consultations.for_patient(appt.patient_id):
            other = await uow.appointments.get(c.appointment_id)
            if other is None or other.id == appt.id:
                continue
            doctor = self._directory.get(c.doctor_id).name
            entries.append(HistoryEntry(c.appointment_id, other.slot.day, doctor, c))
        return tuple(entries)

    def _at(self, day: date) -> datetime:
        return datetime.combine(day, time.min, tzinfo=self._clock.now().tzinfo)
