"""SQL repositories for the staff portal (SPEC 17.4)."""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from clinic_bot.adapters.db.mappers import from_db_time, to_db_time
from clinic_bot.adapters.db.orm import (
    AppointmentRow,
    ClinicDocRow,
    ConsultationRow,
    SlotRow,
    StaffSessionRow,
    StaffUserRow,
)
from clinic_bot.domain.enums import StaffRole
from clinic_bot.domain.errors import Conflict, ErrorCode, NotFound
from clinic_bot.domain.staff import (
    ClinicDoc,
    Consultation,
    ConsultationNote,
    EmailAddress,
    StaffSession,
    StaffUser,
)


def _opt_time(value: datetime | None) -> datetime | None:
    return from_db_time(value) if value else None


def _user(row: StaffUserRow) -> StaffUser:
    return StaffUser(
        id=row.id,
        email=EmailAddress(row.email),
        name=row.name,
        role=StaffRole(row.role),
        doctor_id=row.doctor_id,
        password_hash=row.password_hash,
        active=row.active,
        created_at=from_db_time(row.created_at),
        last_login_at=_opt_time(row.last_login_at),
    )


class SqlStaffUserRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, user_id: int) -> StaffUser | None:
        row = await self._s.get(StaffUserRow, user_id)
        return _user(row) if row else None

    async def by_email(self, email: EmailAddress) -> StaffUser | None:
        row = await self._s.scalar(select(StaffUserRow).where(StaffUserRow.email == email.value))
        return _user(row) if row else None

    async def by_doctor(self, doctor_id: int) -> StaffUser | None:
        stmt = select(StaffUserRow).where(StaffUserRow.doctor_id == doctor_id)
        row = await self._s.scalar(stmt)
        return _user(row) if row else None

    async def all(self) -> list[StaffUser]:
        stmt = select(StaffUserRow).order_by(StaffUserRow.role, StaffUserRow.name)
        return [_user(r) for r in await self._s.scalars(stmt)]

    async def add(self, user: StaffUser) -> StaffUser:
        if await self.by_email(user.email) is not None:
            raise Conflict(ErrorCode.EMAIL_TAKEN)
        if user.doctor_id is not None and await self.by_doctor(user.doctor_id) is not None:
            raise Conflict(ErrorCode.DOCTOR_HAS_ACCOUNT)
        row = StaffUserRow(
            email=user.email.value,
            name=user.name,
            role=user.role.value,
            doctor_id=user.doctor_id,
            password_hash=user.password_hash,
            active=user.active,
            created_at=to_db_time(user.created_at),
            last_login_at=None,
        )
        self._s.add(row)
        try:
            await self._s.flush()
        except IntegrityError as exc:
            raise Conflict(ErrorCode.EMAIL_TAKEN) from exc
        return user.with_id(row.id)

    async def save(self, user: StaffUser) -> None:
        row = await self._s.get(StaffUserRow, user.id)
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND)
        row.name, row.password_hash, row.active = user.name, user.password_hash, user.active
        row.last_login_at = to_db_time(user.last_login_at) if user.last_login_at else None
        await self._s.flush()


class SqlStaffSessionRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, session: StaffSession) -> None:
        self._s.add(
            StaffSessionRow(
                token_hash=session.token_hash,
                user_id=session.user_id,
                created_at=to_db_time(session.created_at),
                expires_at=to_db_time(session.expires_at),
            )
        )
        await self._s.flush()

    async def get(self, token_hash: str) -> StaffSession | None:
        row = await self._s.get(StaffSessionRow, token_hash)
        if row is None:
            return None
        created, expires = from_db_time(row.created_at), from_db_time(row.expires_at)
        return StaffSession(row.token_hash, row.user_id, created, expires)

    async def delete(self, token_hash: str) -> None:
        await self._s.execute(
            delete(StaffSessionRow).where(StaffSessionRow.token_hash == token_hash)
        )

    async def delete_for_user(self, user_id: int, *, keep: str | None = None) -> None:
        stmt = delete(StaffSessionRow).where(StaffSessionRow.user_id == user_id)
        if keep is not None:
            stmt = stmt.where(StaffSessionRow.token_hash != keep)
        await self._s.execute(stmt)

    async def purge_expired(self, now: datetime) -> None:
        stmt = delete(StaffSessionRow).where(StaffSessionRow.expires_at <= to_db_time(now))
        await self._s.execute(stmt)


def _consultation(row: ConsultationRow) -> Consultation:
    note = ConsultationNote(
        notes=row.notes,
        diagnosis=row.diagnosis,
        medication=row.medication,
        followup_required=row.followup_required,
        followup_in_days=row.followup_in_days,
    )
    return Consultation(
        id=row.id,
        appointment_id=row.appointment_id,
        doctor_id=row.doctor_id,
        patient_id=row.patient_id,
        note=note,
        followup_grant_id=row.followup_grant_id,
        submitted_by=row.submitted_by,
        created_at=from_db_time(row.created_at),
        updated_at=from_db_time(row.updated_at),
    )


class SqlConsultationRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def for_appointment(self, appointment_id: int) -> Consultation | None:
        stmt = select(ConsultationRow).where(ConsultationRow.appointment_id == appointment_id)
        row = await self._s.scalar(stmt)
        return _consultation(row) if row else None

    async def for_patient(self, patient_id: int) -> list[Consultation]:
        stmt = (
            select(ConsultationRow)
            .join(AppointmentRow, AppointmentRow.id == ConsultationRow.appointment_id)
            .join(SlotRow, SlotRow.id == AppointmentRow.slot_id)
            .where(ConsultationRow.patient_id == patient_id)
            .order_by(SlotRow.start.desc(), ConsultationRow.id.desc())
        )
        return [_consultation(r) for r in await self._s.scalars(stmt)]

    async def with_consultation(self, appointment_ids: Collection[int]) -> set[int]:
        if not appointment_ids:
            return set()
        stmt = select(ConsultationRow.appointment_id).where(
            ConsultationRow.appointment_id.in_(appointment_ids)
        )
        return set(await self._s.scalars(stmt))

    async def add(self, consultation: Consultation) -> Consultation:
        row = ConsultationRow(appointment_id=consultation.appointment_id)
        self._fill(row, consultation)
        row.created_at = to_db_time(consultation.created_at)
        self._s.add(row)
        try:
            await self._s.flush()
        except IntegrityError as exc:
            raise Conflict(ErrorCode.EXISTS) from exc
        return _consultation(row)

    async def save(self, consultation: Consultation) -> None:
        row = await self._s.get(ConsultationRow, consultation.id)
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND)
        self._fill(row, consultation)
        await self._s.flush()

    @staticmethod
    def _fill(row: ConsultationRow, c: Consultation) -> None:
        row.doctor_id, row.patient_id = c.doctor_id, c.patient_id
        row.notes, row.diagnosis, row.medication = c.note.notes, c.note.diagnosis, c.note.medication
        row.followup_required = c.note.followup_required
        row.followup_in_days = c.note.followup_in_days
        row.followup_grant_id = c.followup_grant_id
        row.submitted_by = c.submitted_by
        row.updated_at = to_db_time(c.updated_at)


def _doc(row: ClinicDocRow) -> ClinicDoc:
    return ClinicDoc(row.name, row.content, _opt_time(row.updated_at), row.updated_by)


class SqlClinicDocRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def all(self) -> list[ClinicDoc]:
        return [_doc(r) for r in await self._s.scalars(select(ClinicDocRow))]

    async def get(self, name: str) -> ClinicDoc | None:
        row = await self._s.get(ClinicDocRow, name)
        return _doc(row) if row else None

    async def save(self, doc: ClinicDoc) -> None:
        row = await self._s.get(ClinicDocRow, doc.name)
        if row is None:
            row = ClinicDocRow(name=doc.name)
            self._s.add(row)
        row.content, row.updated_by = doc.content, doc.updated_by
        row.updated_at = to_db_time(doc.updated_at) if doc.updated_at else None
        await self._s.flush()
