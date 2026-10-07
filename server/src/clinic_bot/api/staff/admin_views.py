"""Response bodies of the admin-only staff API (SPEC 17.3, 17.5). Money is whole rupees."""

from __future__ import annotations

from datetime import date, datetime
from typing import Self

from pydantic import BaseModel

from clinic_bot.domain.staff import ClinicDoc
from clinic_bot.ports.staff import Cell, TablePage
from clinic_bot.services.scheduling import day_label
from clinic_bot.services.staff.clinic import ClosureDay, DoctorAccount


class AccountRefOut(BaseModel):
    id: int
    email: str
    active: bool


class DoctorOut(BaseModel):
    id: int
    name: str
    specialty: str
    specialty_label: str
    bio: str
    consulting_days: list[int]
    days_label: str
    hours: str
    fee_rupees: int
    followup_fee_rupees: int
    account: AccountRefOut | None

    @classmethod
    def of(cls, entry: DoctorAccount) -> Self:
        d, u = entry.doctor, entry.account
        account = (
            AccountRefOut(id=u.id, email=u.email.value, active=u.active) if u and u.id else None
        )
        return cls(
            id=d.id,
            name=d.name,
            specialty=d.specialty.value,
            specialty_label=d.specialty.label,
            bio=d.bio,
            consulting_days=list(d.consulting_days),
            days_label=d.days_label(),
            hours=d.hours,
            fee_rupees=d.fee.paise // 100,
            followup_fee_rupees=d.followup_fee.paise // 100,
            account=account,
        )


class ClinicDocOut(BaseModel):
    name: str
    title: str
    content: str
    updated_at: datetime | None
    updated_by: str | None

    @classmethod
    def of(cls, doc: ClinicDoc) -> Self:
        return cls(
            name=doc.name,
            title=doc.title,
            content=doc.content,
            updated_at=doc.updated_at,
            updated_by=doc.updated_by,
        )


class ClosureOut(BaseModel):
    id: int
    date: date
    date_label: str
    reason: str
    booked_appointments: int

    @classmethod
    def of(cls, entry: ClosureDay) -> Self:
        c = entry.closure
        return cls(
            id=c.id or 0,
            date=c.day,
            date_label=day_label(c.day),
            reason=c.reason,
            booked_appointments=entry.booked_appointments,
        )


class OverviewOut(BaseModel):
    patients: int
    doctors: int
    appointments_today: int
    upcoming_appointments: int
    consultations: int
    chat_summaries: int
    callbacks: int


class TableInfoOut(BaseModel):
    name: str
    row_count: int


class TablePageOut(BaseModel):
    name: str
    columns: list[str]
    rows: list[list[Cell]]
    total: int
    offset: int
    limit: int

    @classmethod
    def of(cls, page: TablePage) -> Self:
        return cls(
            name=page.name,
            columns=list(page.columns),
            rows=[list(r) for r in page.rows],
            total=page.total,
            offset=page.offset,
            limit=page.limit,
        )
