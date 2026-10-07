"""Staff portal ports: accounts, sessions, consultations, clinic docs, table browser."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from clinic_bot.domain.staff import (
    ClinicDoc,
    Consultation,
    EmailAddress,
    StaffSession,
    StaffUser,
)

Cell = str | int | float | bool | None


class StaffUserRepo(Protocol):
    async def get(self, user_id: int) -> StaffUser | None: ...
    async def by_email(self, email: EmailAddress) -> StaffUser | None: ...
    async def by_doctor(self, doctor_id: int) -> StaffUser | None: ...
    async def all(self) -> list[StaffUser]: ...
    async def add(self, user: StaffUser) -> StaffUser:
        """Raises Conflict(EMAIL_TAKEN) or Conflict(DOCTOR_HAS_ACCOUNT)."""
        ...

    async def save(self, user: StaffUser) -> None:
        """Name, password hash, active flag and last login. Raises NotFound."""
        ...


class StaffSessionRepo(Protocol):
    async def add(self, session: StaffSession) -> None: ...
    async def get(self, token_hash: str) -> StaffSession | None: ...
    async def delete(self, token_hash: str) -> None: ...
    async def delete_for_user(self, user_id: int, *, keep: str | None = None) -> None:
        """End every session of ``user_id`` except the one hashed as ``keep``."""
        ...

    async def purge_expired(self, now: datetime) -> None: ...


class ConsultationRepo(Protocol):
    async def for_appointment(self, appointment_id: int) -> Consultation | None: ...
    async def for_patient(self, patient_id: int) -> list[Consultation]:
        """Newest visit first."""
        ...

    async def with_consultation(self, appointment_ids: Collection[int]) -> set[int]: ...
    async def add(self, consultation: Consultation) -> Consultation: ...
    async def save(self, consultation: Consultation) -> None: ...


class ClinicDocRepo(Protocol):
    async def all(self) -> list[ClinicDoc]: ...
    async def get(self, name: str) -> ClinicDoc | None: ...
    async def save(self, doc: ClinicDoc) -> None:
        """Insert or replace by name."""
        ...


@dataclass(frozen=True, slots=True)
class TableInfo:
    name: str
    row_count: int


@dataclass(frozen=True, slots=True)
class TablePage:
    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Cell, ...], ...]
    total: int
    offset: int
    limit: int


class TableBrowser(Protocol):
    """Read-only view of every table for the admin. Secrets are never exposed."""

    async def tables(self) -> list[TableInfo]: ...
    async def page(self, name: str, offset: int, limit: int) -> TablePage:
        """Rows in primary-key order. Raises NotFound for unknown or hidden tables."""
        ...

    async def counts(self, names: Sequence[str]) -> dict[str, int]: ...
