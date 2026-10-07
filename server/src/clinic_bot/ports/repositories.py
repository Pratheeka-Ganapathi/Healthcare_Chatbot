"""Repository ports. Implementations map storage rows to domain objects."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import date, datetime
from typing import Protocol

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
from clinic_bot.domain.enums import Sex, TimePref
from clinic_bot.domain.values import DateOfBirth, PersonName, PhoneNumber


class PatientRepo(Protocol):
    async def by_phone(self, phone: PhoneNumber) -> Patient | None: ...
    async def get(self, patient_id: int) -> Patient | None: ...
    async def many(self, patient_ids: Collection[int]) -> dict[int, Patient]: ...
    async def add(
        self, name: PersonName, phone: PhoneNumber, dob: DateOfBirth, sex: Sex, created_at: datetime
    ) -> Patient:
        """Raises NotFound(NO_MATCH) if the phone is already registered."""
        ...


class DoctorRepo(Protocol):
    async def all(self) -> list[Doctor]: ...
    async def require(self, doctor_id: int) -> Doctor:
        """Raises NotFound."""
        ...

    async def save(self, doctor: Doctor) -> None:
        """Name, bio and fees. Raises NotFound."""
        ...


class SlotRepo(Protocol):
    async def require(self, slot_id: int) -> Slot:
        """Raises NotFound."""
        ...

    async def free(
        self,
        doctor_id: int,
        day: date,
        time_pref: TimePref,
        not_before: datetime,
        limit: int,
    ) -> list[Slot]:
        """Unbooked slots for one doctor on one day, earliest first."""
        ...


class ClosureRepo(Protocol):
    async def on(self, day: date) -> Closure | None: ...
    async def from_day(self, day: date) -> list[Closure]:
        """Closures on ``day`` or later, earliest first."""
        ...

    async def add(self, closure: Closure) -> Closure:
        """Raises Conflict(EXISTS) if the day is already closed."""
        ...

    async def delete(self, closure_id: int) -> None:
        """Raises NotFound."""
        ...


class AppointmentRepo(Protocol):
    async def get(self, appointment_id: int) -> Appointment | None: ...
    async def by_session_slot(self, session_id: str, slot_id: int) -> Appointment | None: ...
    async def upcoming_for_patient(self, patient_id: int, now: datetime) -> list[Appointment]: ...
    async def add(self, appointment: Appointment, session_id: str) -> Appointment:
        """Persist a new booking. Raises SlotTaken if the slot is already booked."""
        ...

    async def save(self, appointment: Appointment) -> None:
        """Status, cancellation time and intake."""
        ...

    async def between(
        self,
        start: datetime,
        end: datetime,
        *,
        doctor_id: int | None = None,
        newest_first: bool = False,
    ) -> list[Appointment]:
        """Appointments whose slot starts in ``[start, end)``, any status."""
        ...


class FollowupRepo(Protocol):
    async def active(
        self, patient_id: int, doctor_id: int, today: date
    ) -> FollowupGrant | None: ...
    async def get(self, grant_id: int) -> FollowupGrant | None: ...
    async def save(self, grant: FollowupGrant) -> None:
        """Validity and use."""
        ...

    async def add(
        self,
        patient_id: int,
        doctor_id: int,
        source_appointment_id: int,
        valid_until: date,
        created_by: str,
    ) -> FollowupGrant: ...
    async def delete(self, grant_id: int) -> None: ...


class VerifyAttemptRepo(Protocol):
    async def add(self, attempt: VerifyAttempt) -> None: ...
    async def since(self, phone_norm: str, since: datetime) -> list[VerifyAttempt]: ...


class CallbackRepo(Protocol):
    async def add(self, callback: Callback) -> Callback: ...


class ChatSummaryRepo(Protocol):
    async def add(self, summary: ChatSummary) -> ChatSummary: ...
    async def for_patient(self, patient_id: int) -> list[ChatSummary]:
        """Newest first."""
        ...


class TranscriptRepo(Protocol):
    async def add_many(self, records: Sequence[TranscriptRecord]) -> None: ...
