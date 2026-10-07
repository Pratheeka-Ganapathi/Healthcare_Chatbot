"""In-memory repositories and Unit of Work that behave like the SQL adapters."""

from __future__ import annotations

import copy
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from typing import Self

from clinic_bot.domain.entities import (
    Appointment,
    Callback,
    ChatSummary,
    Closure,
    Doctor,
    FollowupGrant,
    Patient,
    Slot,
    TranscriptRecord,
    VerifyAttempt,
)
from clinic_bot.domain.enums import AppointmentStatus, Sex, TimePref
from clinic_bot.domain.errors import Conflict, ErrorCode, NotFound, SlotTaken
from clinic_bot.domain.policies import SlotTimingPolicy
from clinic_bot.domain.staff import ClinicDoc, Consultation
from clinic_bot.domain.values import DateOfBirth, PersonName, PhoneNumber
from tests.fakes.staff_repos import (
    InMemoryClinicDocRepo,
    InMemoryConsultationRepo,
    InMemoryStaffSessionRepo,
    InMemoryStaffUserRepo,
    StaffStore,
)


@dataclass
class Store:
    patients: dict[int, Patient] = field(default_factory=dict)
    doctors: dict[int, Doctor] = field(default_factory=dict)
    slots: dict[int, Slot] = field(default_factory=dict)
    closures: dict[date, Closure] = field(default_factory=dict)
    appointments: dict[int, tuple[Appointment, str]] = field(default_factory=dict)
    grants: dict[int, FollowupGrant] = field(default_factory=dict)
    attempts: list[VerifyAttempt] = field(default_factory=list)
    callbacks: list[Callback] = field(default_factory=list)
    transcripts: list[TranscriptRecord] = field(default_factory=list)
    chat_summaries: list[ChatSummary] = field(default_factory=list)
    staff: StaffStore = field(default_factory=StaffStore)
    consultations: dict[int, Consultation] = field(default_factory=dict)
    clinic_docs: dict[str, ClinicDoc] = field(default_factory=dict)


class _Repos:
    def __init__(self, store: Store) -> None:
        self.s = store


class InMemoryPatientRepo(_Repos):
    async def by_phone(self, phone: PhoneNumber) -> Patient | None:
        return next((p for p in self.s.patients.values() if p.phone == phone), None)

    async def get(self, patient_id: int) -> Patient | None:
        return self.s.patients.get(patient_id)

    async def many(self, patient_ids: Collection[int]) -> dict[int, Patient]:
        return {i: self.s.patients[i] for i in patient_ids if i in self.s.patients}

    async def add(
        self, name: PersonName, phone: PhoneNumber, dob: DateOfBirth, sex: Sex, created_at: datetime
    ) -> Patient:
        if await self.by_phone(phone) is not None:
            raise NotFound(ErrorCode.NO_MATCH)
        patient = Patient(max(self.s.patients, default=0) + 1, name.value, phone, dob, sex)
        self.s.patients[patient.id] = patient
        return patient


class InMemoryDoctorRepo(_Repos):
    async def all(self) -> list[Doctor]:
        return [self.s.doctors[k] for k in sorted(self.s.doctors)]

    async def require(self, doctor_id: int) -> Doctor:
        if doctor_id not in self.s.doctors:
            raise NotFound(ErrorCode.NOT_FOUND)
        return self.s.doctors[doctor_id]

    async def save(self, doctor: Doctor) -> None:
        if doctor.id not in self.s.doctors:
            raise NotFound(ErrorCode.NOT_FOUND)
        self.s.doctors[doctor.id] = doctor


class InMemorySlotRepo(_Repos):
    async def require(self, slot_id: int) -> Slot:
        if slot_id not in self.s.slots:
            raise NotFound(ErrorCode.NOT_FOUND)
        return self.s.slots[slot_id]

    async def free(
        self, doctor_id: int, day: date, time_pref: TimePref, not_before: datetime, limit: int
    ) -> list[Slot]:
        booked = {
            a.slot.id
            for a, _ in self.s.appointments.values()
            if a.status is AppointmentStatus.BOOKED
        }
        tz = not_before.tzinfo
        lo = datetime.combine(day, time.min, tz)
        hi = datetime.combine(day + timedelta(days=1), time.min, tz)
        if time_pref is TimePref.MORNING:
            hi = datetime.combine(day, time(SlotTimingPolicy.MORNING_END_HOUR), tz)
        elif time_pref is TimePref.EVENING:
            lo = datetime.combine(day, time(SlotTimingPolicy.EVENING_START_HOUR), tz)
        found = [
            s
            for s in self.s.slots.values()
            if s.doctor_id == doctor_id
            and max(lo, not_before) <= s.start < hi
            and s.id not in booked
        ]
        return sorted(found, key=lambda s: s.start)[:limit]


class InMemoryClosureRepo(_Repos):
    async def on(self, day: date) -> Closure | None:
        return self.s.closures.get(day)

    async def from_day(self, day: date) -> list[Closure]:
        return [self.s.closures[d] for d in sorted(self.s.closures) if d >= day]

    async def add(self, closure: Closure) -> Closure:
        if closure.day in self.s.closures:
            raise Conflict(ErrorCode.EXISTS)
        new_id = max((c.id or 0 for c in self.s.closures.values()), default=0) + 1
        saved = replace(closure, id=new_id)
        self.s.closures[closure.day] = saved
        return saved

    async def delete(self, closure_id: int) -> None:
        day = next((d for d, c in self.s.closures.items() if c.id == closure_id), None)
        if day is None:
            raise NotFound(ErrorCode.NOT_FOUND)
        del self.s.closures[day]


class InMemoryAppointmentRepo(_Repos):
    async def get(self, appointment_id: int) -> Appointment | None:
        found = self.s.appointments.get(appointment_id)
        return copy.deepcopy(found[0]) if found else None

    async def by_session_slot(self, session_id: str, slot_id: int) -> Appointment | None:
        for appt, sid in self.s.appointments.values():
            if (
                sid == session_id
                and appt.slot.id == slot_id
                and appt.status is AppointmentStatus.BOOKED
            ):
                return copy.deepcopy(appt)
        return None

    async def upcoming_for_patient(self, patient_id: int, now: datetime) -> list[Appointment]:
        found = [
            copy.deepcopy(a)
            for a, _ in self.s.appointments.values()
            if a.patient_id == patient_id
            and a.status is AppointmentStatus.BOOKED
            and a.slot.start >= now
        ]
        return sorted(found, key=lambda a: a.slot.start)

    async def add(self, appointment: Appointment, session_id: str) -> Appointment:
        for appt, _sid in self.s.appointments.values():
            same_slot = appt.slot.id == appointment.slot.id
            if same_slot and appt.status is AppointmentStatus.BOOKED:
                raise SlotTaken(ErrorCode.SLOT_TAKEN)
        appointment.id = max(self.s.appointments, default=0) + 1
        self.s.appointments[appointment.id] = (copy.deepcopy(appointment), session_id)
        return appointment

    async def save(self, appointment: Appointment) -> None:
        if appointment.id is None or appointment.id not in self.s.appointments:
            raise NotFound(ErrorCode.NOT_FOUND)
        session = self.s.appointments[appointment.id][1]
        self.s.appointments[appointment.id] = (copy.deepcopy(appointment), session)

    async def between(
        self,
        start: datetime,
        end: datetime,
        *,
        doctor_id: int | None = None,
        newest_first: bool = False,
    ) -> list[Appointment]:
        found = [
            copy.deepcopy(a)
            for a, _ in self.s.appointments.values()
            if start <= a.slot.start < end and doctor_id in (None, a.doctor_id)
        ]
        found.sort(key=lambda a: (a.slot.start, a.id or 0))
        if newest_first:
            found.sort(key=lambda a: a.slot.start, reverse=True)
        return found


class InMemoryFollowupRepo(_Repos):
    async def active(self, patient_id: int, doctor_id: int, today: date) -> FollowupGrant | None:
        found = [
            g
            for g in self.s.grants.values()
            if g.patient_id == patient_id and g.doctor_id == doctor_id and g.is_active(today)
        ]
        return copy.deepcopy(max(found, key=lambda g: g.valid_until)) if found else None

    async def get(self, grant_id: int) -> FollowupGrant | None:
        return copy.deepcopy(self.s.grants.get(grant_id))

    async def save(self, grant: FollowupGrant) -> None:
        if grant.id not in self.s.grants:
            raise NotFound(ErrorCode.NOT_FOUND)
        self.s.grants[grant.id] = copy.deepcopy(grant)

    async def add(
        self,
        patient_id: int,
        doctor_id: int,
        source_appointment_id: int,
        valid_until: date,
        created_by: str,
    ) -> FollowupGrant:
        new_id = max(self.s.grants, default=0) + 1
        grant = FollowupGrant(
            new_id, patient_id, doctor_id, source_appointment_id, valid_until, created_by
        )
        self.s.grants[new_id] = grant
        return copy.deepcopy(grant)

    async def delete(self, grant_id: int) -> None:
        self.s.grants.pop(grant_id, None)


class InMemoryVerifyAttemptRepo(_Repos):
    async def add(self, attempt: VerifyAttempt) -> None:
        self.s.attempts.append(attempt)

    async def since(self, phone_norm: str, since: datetime) -> list[VerifyAttempt]:
        return sorted(
            (a for a in self.s.attempts if a.phone_norm == phone_norm and a.ts >= since),
            key=lambda a: a.ts,
        )


class InMemoryCallbackRepo(_Repos):
    async def add(self, callback: Callback) -> Callback:
        saved = callback.with_id(len(self.s.callbacks) + 1)
        self.s.callbacks.append(saved)
        return saved


class InMemoryChatSummaryRepo(_Repos):
    async def add(self, summary: ChatSummary) -> ChatSummary:
        saved = summary.with_id(len(self.s.chat_summaries) + 1)
        self.s.chat_summaries.append(saved)
        return saved

    async def for_patient(self, patient_id: int) -> list[ChatSummary]:
        mine = [c for c in self.s.chat_summaries if c.patient_id == patient_id]
        return sorted(mine, key=lambda c: (c.created_at, c.id or 0), reverse=True)


class InMemoryTranscriptRepo(_Repos):
    async def add_many(self, records: Sequence[TranscriptRecord]) -> None:
        self.s.transcripts.extend(records)


class InMemoryUnitOfWork:
    """Copy-on-enter, swap-on-commit: uncommitted work is discarded like a rollback."""

    def __init__(self, store: Store) -> None:
        self._committed_store = store

    async def __aenter__(self) -> Self:
        self._work = copy.deepcopy(self._committed_store)
        self.patients = InMemoryPatientRepo(self._work)
        self.doctors = InMemoryDoctorRepo(self._work)
        self.slots = InMemorySlotRepo(self._work)
        self.closures = InMemoryClosureRepo(self._work)
        self.appointments = InMemoryAppointmentRepo(self._work)
        self.followups = InMemoryFollowupRepo(self._work)
        self.verify_attempts = InMemoryVerifyAttemptRepo(self._work)
        self.callbacks = InMemoryCallbackRepo(self._work)
        self.transcripts = InMemoryTranscriptRepo(self._work)
        self.chat_summaries = InMemoryChatSummaryRepo(self._work)
        self.staff_users = InMemoryStaffUserRepo(self._work.staff)
        self.staff_sessions = InMemoryStaffSessionRepo(self._work.staff)
        work = self._work
        self.consultations = InMemoryConsultationRepo(
            work.consultations, lambda i: work.appointments[i][0].slot.start
        )
        self.clinic_docs = InMemoryClinicDocRepo(self._work.clinic_docs)
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def commit(self) -> None:
        for name in vars(self._committed_store):
            setattr(self._committed_store, name, getattr(self._work, name))


class InMemoryUnitOfWorkFactory:
    def __init__(self, store: Store | None = None) -> None:
        self.store = store or Store()

    def __call__(self, *, write: bool = False) -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(self.store)


def with_status(appt: Appointment, status: AppointmentStatus) -> Appointment:
    return replace(appt, status=status)
