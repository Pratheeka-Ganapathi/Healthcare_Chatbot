"""Entities. Each owns its own invariants and behaviour."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import TYPE_CHECKING

from clinic_bot.domain.enums import (
    AppointmentStatus,
    CallbackPriority,
    Sex,
    Specialty,
    VisitType,
)
from clinic_bot.domain.errors import Conflict, ErrorCode, InvalidInput, NotFound, NotOwner
from clinic_bot.domain.values import DateOfBirth, Money, PersonName, PhoneNumber, TimeWindow

if TYPE_CHECKING:
    from clinic_bot.domain.policies import CancellationPolicy


@dataclass(frozen=True, slots=True)
class Patient:
    id: int
    name: str
    phone: PhoneNumber
    dob: DateOfBirth
    sex: Sex

    def matches(self, phone: PhoneNumber, dob: DateOfBirth) -> bool:
        return self.phone == phone and self.dob == dob

    def matches_registration(self, name: PersonName, phone: PhoneNumber, dob: DateOfBirth) -> bool:
        """A returning patient re-registering: every detail must match the record."""
        return self.matches(phone, dob) and name.same_as(self.name)

    def age_on(self, today: date) -> int:
        return self.dob.age_on(today)


@dataclass(frozen=True, slots=True)
class Doctor:
    id: int
    name: str
    specialty: Specialty
    bio: str
    consulting_days: tuple[int, ...]  # 0 = Monday
    hours: str
    fee: Money
    followup_fee: Money

    def days_label(self) -> str:
        names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        return ", ".join(names[d] for d in self.consulting_days)


@dataclass(frozen=True, slots=True)
class Slot:
    id: int
    doctor_id: int
    window: TimeWindow

    @property
    def start(self) -> datetime:
        return self.window.start

    @property
    def day(self) -> date:
        return self.window.start.date()


@dataclass(frozen=True, slots=True)
class Closure:
    day: date
    reason: str
    id: int | None = None


@dataclass(frozen=True, slots=True)
class IntakeAnswer:
    q: str
    a: str


@dataclass(frozen=True, slots=True)
class IntakeSummary:
    chief_complaint: str
    duration: str | None = None
    severity: int | None = None
    answers: tuple[IntakeAnswer, ...] = ()
    red_flags_checked: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.chief_complaint.strip():
            raise InvalidInput(ErrorCode.INVALID, "chief_complaint is empty")
        if self.severity is not None and not 1 <= self.severity <= 10:
            raise InvalidInput(ErrorCode.INVALID, "severity must be 1-10")

    def to_dict(self) -> dict[str, object]:
        return {
            "chief_complaint": self.chief_complaint,
            "duration": self.duration,
            "severity": self.severity,
            "answers": [{"q": a.q, "a": a.a} for a in self.answers],
            "red_flags_checked": list(self.red_flags_checked),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> IntakeSummary:
        raw_answers = data.get("answers")
        raw_flags = data.get("red_flags_checked")
        severity = data.get("severity")
        duration = data.get("duration")
        answers = (
            [a for a in raw_answers if isinstance(a, Mapping)]
            if isinstance(raw_answers, list)
            else []
        )
        flags = [str(f) for f in raw_flags] if isinstance(raw_flags, list) else []
        return cls(
            chief_complaint=str(data.get("chief_complaint", "")),
            duration=str(duration) if duration is not None else None,
            severity=severity if isinstance(severity, int) else None,
            answers=tuple(
                IntakeAnswer(q=str(a.get("q", "")), a=str(a.get("a", ""))) for a in answers
            ),
            red_flags_checked=tuple(flags),
        )


@dataclass(slots=True)
class Appointment:
    id: int | None
    patient_id: int
    doctor_id: int
    slot: Slot
    visit_type: VisitType
    fee: Money
    status: AppointmentStatus
    intake: IntakeSummary | None
    followup_grant_id: int | None = None
    cancelled_at: datetime | None = None

    @classmethod
    def book(
        cls,
        patient_id: int,
        slot: Slot,
        visit_type: VisitType,
        fee: Money,
        intake: IntakeSummary | None,
        followup_grant_id: int | None = None,
    ) -> Appointment:
        return cls(
            id=None,
            patient_id=patient_id,
            doctor_id=slot.doctor_id,
            slot=slot,
            visit_type=visit_type,
            fee=fee,
            status=AppointmentStatus.BOOKED,
            intake=intake,
            followup_grant_id=followup_grant_id,
        )

    def ensure_owner(self, patient_id: int) -> None:
        if self.patient_id != patient_id:
            raise NotOwner(ErrorCode.NOT_OWNER)

    def cancel(self, now: datetime, policy: CancellationPolicy) -> None:
        if self.status is not AppointmentStatus.BOOKED:
            raise NotFound(ErrorCode.NOT_FOUND)
        policy.ensure_cancellable(self.slot.start, now)
        self.status = AppointmentStatus.CANCELLED
        self.cancelled_at = now

    def ensure_recordable(self, today: date) -> None:
        """Doctors record outcomes only for visits on or before today, never cancelled ones."""
        if self.status is AppointmentStatus.CANCELLED or self.slot.day > today:
            raise Conflict(ErrorCode.NOT_RECORDABLE)

    def record_outcome(self, status: AppointmentStatus, today: date) -> None:
        """Booked, completed or no-show. Cancelling stays with the patient."""
        if status is AppointmentStatus.CANCELLED:
            raise InvalidInput(ErrorCode.INVALID, "doctors cannot cancel")
        self.ensure_recordable(today)
        self.status = status

    def revise_intake(
        self, chief_complaint: str, duration: str | None, severity: int | None, today: date
    ) -> None:
        """The doctor corrects the visit details; the bot's Q&A answers are kept."""
        self.ensure_recordable(today)
        old = self.intake
        self.intake = IntakeSummary(
            chief_complaint=chief_complaint.strip(),
            duration=(duration or "").strip() or None,
            severity=severity,
            answers=old.answers if old else (),
            red_flags_checked=old.red_flags_checked if old else (),
        )


@dataclass(slots=True)
class FollowupGrant:
    id: int
    patient_id: int
    doctor_id: int
    source_appointment_id: int | None
    valid_until: date
    created_by: str
    used_appointment_id: int | None = None

    def is_active(self, today: date) -> bool:
        return self.used_appointment_id is None and self.valid_until >= today

    def mark_used(self, appointment_id: int) -> None:
        self.used_appointment_id = appointment_id

    @property
    def used(self) -> bool:
        return self.used_appointment_id is not None


@dataclass(frozen=True, slots=True)
class VerifyAttempt:
    phone_norm: str
    ts: datetime
    success: bool


@dataclass(frozen=True, slots=True)
class Callback:
    id: int | None
    patient_id: int | None
    reason: str
    summary: str
    priority: CallbackPriority
    created_at: datetime

    def ticket(self) -> str:
        if self.id is None:
            raise ValueError("callback not saved yet")
        return f"CB-{self.id:04d}"

    def with_id(self, new_id: int) -> Callback:
        return replace(self, id=new_id)


@dataclass(frozen=True, slots=True)
class ChatSummary:
    """A finished chat, summarised for the patient's record."""

    id: int | None
    patient_id: int
    session_id: str
    summary: str
    created_at: datetime

    def with_id(self, new_id: int) -> ChatSummary:
        return replace(self, id=new_id)


@dataclass(frozen=True, slots=True)
class TranscriptRecord:
    session_id: str
    patient_id: int | None
    turns: Sequence[Mapping[str, str]] = field(default_factory=tuple)
    guardrail_events: Sequence[Mapping[str, str]] = field(default_factory=tuple)
    created_at: datetime | None = None
