"""In-memory staff portal repositories that behave like the SQL adapters."""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass, field, replace
from datetime import datetime

from clinic_bot.domain.errors import Conflict, ErrorCode, NotFound
from clinic_bot.domain.staff import (
    ClinicDoc,
    Consultation,
    EmailAddress,
    StaffSession,
    StaffUser,
)


@dataclass
class StaffStore:
    users: dict[int, StaffUser] = field(default_factory=dict)
    sessions: dict[str, StaffSession] = field(default_factory=dict)


class InMemoryStaffUserRepo:
    def __init__(self, store: StaffStore) -> None:
        self.s = store

    async def get(self, user_id: int) -> StaffUser | None:
        return self.s.users.get(user_id)

    async def by_email(self, email: EmailAddress) -> StaffUser | None:
        return next((u for u in self.s.users.values() if u.email == email), None)

    async def by_doctor(self, doctor_id: int) -> StaffUser | None:
        return next((u for u in self.s.users.values() if u.doctor_id == doctor_id), None)

    async def all(self) -> list[StaffUser]:
        return sorted(self.s.users.values(), key=lambda u: (u.role.value, u.name))

    async def add(self, user: StaffUser) -> StaffUser:
        if await self.by_email(user.email) is not None:
            raise Conflict(ErrorCode.EMAIL_TAKEN)
        if user.doctor_id is not None and await self.by_doctor(user.doctor_id) is not None:
            raise Conflict(ErrorCode.DOCTOR_HAS_ACCOUNT)
        saved = user.with_id(max(self.s.users, default=0) + 1)
        assert saved.id is not None
        self.s.users[saved.id] = saved
        return saved

    async def save(self, user: StaffUser) -> None:
        if user.id not in self.s.users:
            raise NotFound(ErrorCode.NOT_FOUND)
        self.s.users[user.id] = user


class InMemoryStaffSessionRepo:
    def __init__(self, store: StaffStore) -> None:
        self.s = store

    async def add(self, session: StaffSession) -> None:
        self.s.sessions[session.token_hash] = session

    async def get(self, token_hash: str) -> StaffSession | None:
        return self.s.sessions.get(token_hash)

    async def delete(self, token_hash: str) -> None:
        self.s.sessions.pop(token_hash, None)

    async def delete_for_user(self, user_id: int, *, keep: str | None = None) -> None:
        self.s.sessions = {
            h: s for h, s in self.s.sessions.items() if s.user_id != user_id or h == keep
        }

    async def purge_expired(self, now: datetime) -> None:
        self.s.sessions = {h: s for h, s in self.s.sessions.items() if s.expires_at > now}


class InMemoryConsultationRepo:
    def __init__(
        self, store: dict[int, Consultation], visit_start: Callable[[int], datetime]
    ) -> None:
        self.s, self._visit_start = store, visit_start

    async def for_appointment(self, appointment_id: int) -> Consultation | None:
        return next((c for c in self.s.values() if c.appointment_id == appointment_id), None)

    async def for_patient(self, patient_id: int) -> list[Consultation]:
        mine = [c for c in self.s.values() if c.patient_id == patient_id]
        return sorted(
            mine, key=lambda c: (self._visit_start(c.appointment_id), c.id or 0), reverse=True
        )

    async def with_consultation(self, appointment_ids: Collection[int]) -> set[int]:
        return {c.appointment_id for c in self.s.values()} & set(appointment_ids)

    async def add(self, consultation: Consultation) -> Consultation:
        if await self.for_appointment(consultation.appointment_id) is not None:
            raise Conflict(ErrorCode.EXISTS)
        saved = replace(consultation, id=max(self.s, default=0) + 1)
        assert saved.id is not None
        self.s[saved.id] = saved
        return saved

    async def save(self, consultation: Consultation) -> None:
        if consultation.id not in self.s:
            raise NotFound(ErrorCode.NOT_FOUND)
        self.s[consultation.id] = consultation


class InMemoryClinicDocRepo:
    def __init__(self, store: dict[str, ClinicDoc]) -> None:
        self.s = store

    async def all(self) -> list[ClinicDoc]:
        return list(self.s.values())

    async def get(self, name: str) -> ClinicDoc | None:
        return self.s.get(name)

    async def save(self, doc: ClinicDoc) -> None:
        self.s[doc.name] = doc
