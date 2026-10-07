"""Staff portal: accounts, sessions, consultations, editable clinic documents (SPEC 17)."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

from clinic_bot.domain.enums import StaffRole
from clinic_bot.domain.errors import ErrorCode, InvalidInput

MIN_PASSWORD = 8
MAX_PASSWORD = 128
MAX_NOTE_CHARS = 5000
MAX_DOC_CHARS = 50_000
FOLLOWUP_DAYS_MIN, FOLLOWUP_DAYS_MAX = 1, 90
# The FAQ documents an admin may edit. The specialty guide and intake checklists drive
# routing and stay in data/docs.
EDITABLE_DOCS = {
    "clinic_info.md": "Clinic information",
    "services.md": "Services",
    "insurance.md": "Insurance",
    "prep_sheets.md": "Preparation sheets",
}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_HEADING = re.compile(r"^# \S", re.MULTILINE)  # the index splits documents on these


@dataclass(frozen=True, slots=True)
class EmailAddress:
    value: str

    def __post_init__(self) -> None:
        if (
            len(self.value) > 254
            or not _EMAIL.match(self.value)
            or self.value != self.value.lower()
        ):
            raise InvalidInput(ErrorCode.BAD_EMAIL)

    @classmethod
    def parse(cls, raw: str) -> EmailAddress:
        return cls(raw.strip().lower())


def check_password(raw: str) -> str:
    """Raises ``InvalidInput(WEAK_PASSWORD)`` outside 8 to 128 characters."""
    if not MIN_PASSWORD <= len(raw) <= MAX_PASSWORD:
        raise InvalidInput(ErrorCode.WEAK_PASSWORD)
    return raw


def check_staff_name(raw: str) -> str:
    name = " ".join(raw.split())
    if not 2 <= len(name) <= 80:
        raise InvalidInput(ErrorCode.BAD_NAME)
    return name


@dataclass(frozen=True, slots=True)
class StaffUser:
    id: int | None
    email: EmailAddress
    name: str
    role: StaffRole
    doctor_id: int | None
    password_hash: str
    active: bool
    created_at: datetime
    last_login_at: datetime | None = None

    def __post_init__(self) -> None:
        if (self.role is StaffRole.DOCTOR) != (self.doctor_id is not None):
            raise InvalidInput(ErrorCode.INVALID, "a doctor account links exactly one doctor")

    @property
    def is_admin(self) -> bool:
        return self.role is StaffRole.ADMIN

    def with_id(self, new_id: int) -> StaffUser:
        return replace(self, id=new_id)


@dataclass(frozen=True, slots=True)
class StaffSession:
    token_hash: str
    user_id: int
    created_at: datetime
    expires_at: datetime

    @classmethod
    def start(cls, token_hash: str, user_id: int, now: datetime, hours: int) -> StaffSession:
        return cls(token_hash, user_id, now, now + timedelta(hours=hours))

    def is_live(self, now: datetime) -> bool:
        return now < self.expires_at


@dataclass(frozen=True, slots=True)
class ConsultationNote:
    """What the doctor submits. Follow-up days only when follow-up is ticked."""

    notes: str
    diagnosis: str
    medication: str
    followup_required: bool
    followup_in_days: int | None

    def __post_init__(self) -> None:
        if any(len(t) > MAX_NOTE_CHARS for t in (self.notes, self.diagnosis, self.medication)):
            raise InvalidInput(ErrorCode.INVALID, "note too long")
        days = self.followup_in_days
        if self.followup_required and (
            days is None or not FOLLOWUP_DAYS_MIN <= days <= FOLLOWUP_DAYS_MAX
        ):
            raise InvalidInput(ErrorCode.INVALID, "follow-up days must be 1-90")
        if not self.followup_required and days is not None:
            raise InvalidInput(ErrorCode.INVALID, "follow-up days without follow-up")

    def followup_until(self, visit_day: date) -> date | None:
        if self.followup_in_days is None:
            return None
        return visit_day + timedelta(days=self.followup_in_days)


@dataclass(frozen=True, slots=True)
class Consultation:
    id: int | None
    appointment_id: int
    doctor_id: int
    patient_id: int
    note: ConsultationNote
    followup_grant_id: int | None
    submitted_by: int  # staff user id
    created_at: datetime
    updated_at: datetime

    def revised(
        self, note: ConsultationNote, grant_id: int | None, by: int, now: datetime
    ) -> Consultation:
        return replace(self, note=note, followup_grant_id=grant_id, submitted_by=by, updated_at=now)


@dataclass(frozen=True, slots=True)
class ClinicDoc:
    name: str
    content: str
    updated_at: datetime | None = None
    updated_by: str | None = None

    def __post_init__(self) -> None:
        if self.name not in EDITABLE_DOCS:
            raise InvalidInput(ErrorCode.INVALID, "not an editable document")
        if len(self.content) > MAX_DOC_CHARS:
            raise InvalidInput(ErrorCode.INVALID, "document too long")
        if not _HEADING.search(self.content):
            raise InvalidInput(ErrorCode.NO_HEADING)

    @property
    def title(self) -> str:
        return EDITABLE_DOCS[self.name]
