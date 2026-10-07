"""Synthetic demo data, laid out relative to ``clock.now()`` (SPEC 9.1)."""

from __future__ import annotations

import random
from collections.abc import Collection
from datetime import date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from clinic_bot.adapters.db.mappers import to_db_time
from clinic_bot.adapters.db.orm import (
    AppointmentRow,
    Base,
    ClinicDocRow,
    ClosureRow,
    DoctorRow,
    FollowupGrantRow,
    PatientRow,
    SlotRow,
)
from clinic_bot.domain.staff import EDITABLE_DOCS
from clinic_bot.ports.clock import Clock
from clinic_bot.seed.demo_data import (
    DOCTORS,
    PATIENTS,
    PREBOOK_RATE,
    SEED_SESSION,
    SLOT_MINUTES,
    WINDOW_DAYS,
    DoctorSeed,
)


class Seeder:
    """Creates and fills the schema. Deterministic for a given ``now``."""

    def __init__(self, engine: AsyncEngine, clock: Clock, docs_dir: Path | None = None) -> None:
        """``docs_dir``: where the editable clinic docs are first read from (SPEC 17.3)."""
        self._engine, self._clock, self._docs_dir = engine, clock, docs_dir
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def reseed(self) -> None:
        """Drop everything and start from the demo data (``make reseed``, tests)."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await self.ensure_seeded()

    async def ensure_seeded(self) -> None:
        """Startup: create missing tables, fill an empty database, else top up slots."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with self._sessions() as session:
            if await session.scalar(select(func.count()).select_from(PatientRow)):
                await self._top_up_slots(session)
            else:
                await self._fill(session)
            await self._seed_docs(session)
            await session.commit()

    async def _seed_docs(self, session: AsyncSession) -> None:
        """Admin-editable docs start as the authored files; later edits are never overwritten."""
        if self._docs_dir is None or await session.scalar(
            select(func.count()).select_from(ClinicDocRow)
        ):
            return
        docs_dir = self._docs_dir
        session.add_all(
            ClinicDocRow(name=name, content=(docs_dir / name).read_text(encoding="utf-8"))
            for name in EDITABLE_DOCS
        )

    async def _top_up_slots(self, session: AsyncSession) -> None:
        """Keep the booking window open on a long-lived database. Existing slots stay."""
        today = self._clock.now().date()
        ids = {d.name: d.id for d in await session.scalars(select(DoctorRow))}
        closed = set(await session.scalars(select(ClosureRow.date)))
        rows = [
            {"doctor_id": s.doctor_id, "start": s.start, "end": s.end}
            for seed in DOCTORS
            if seed.name in ids
            for s in _slots(ids[seed.name], seed, today, closed)
        ]
        if rows:
            stmt = insert(SlotRow).values(rows).on_conflict_do_nothing()
            await session.execute(stmt)

    async def _fill(self, session: AsyncSession) -> None:
        now = self._clock.now()
        created = to_db_time(now)
        patients = [
            PatientRow(name=p.name, phone=p.phone, dob=p.dob, sex=p.sex, created_at=created)
            for p in PATIENTS
        ]
        doctors = [_doctor_row(d) for d in DOCTORS]
        session.add_all([*patients, *doctors])
        closure_day = _closure_day(now.date())
        session.add(ClosureRow(date=closure_day, reason="Clinic closed for staff training"))
        await session.flush()
        slots = [
            s
            for d, seed in zip(doctors, DOCTORS, strict=True)
            for s in _slots(d.id, seed, now.date(), {closure_day})
        ]
        session.add_all(slots)
        await session.flush()
        await _book_demo_state(session, now, patients, doctors, slots)


def _doctor_row(d: DoctorSeed) -> DoctorRow:
    return DoctorRow(
        name=d.name,
        specialty=d.specialty,
        bio=d.bio,
        consulting_days=",".join(str(x) for x in d.days),
        hours=d.hours_label(),
        fee=d.fee_rupees * 100,
        followup_fee=d.followup_rupees * 100,
    )


def _closure_day(today: date) -> date:
    day = today + timedelta(days=3)
    return day + timedelta(days=1) if day.weekday() == 6 else day


def _slots(
    doctor_id: int, seed: DoctorSeed, today: date, closed: Collection[date]
) -> list[SlotRow]:
    rows: list[SlotRow] = []
    step = timedelta(minutes=SLOT_MINUTES)
    for offset in range(WINDOW_DAYS + 1):
        day = today + timedelta(days=offset)
        if day in closed or day.weekday() not in seed.days:
            continue
        for start_t, end_t in seed.sessions:
            cursor, end = datetime.combine(day, start_t), datetime.combine(day, end_t)
            while cursor + step <= end:
                rows.append(SlotRow(doctor_id=doctor_id, start=cursor, end=cursor + step))
                cursor += step
    return rows


async def _book_demo_state(
    session: AsyncSession,
    now: datetime,
    patients: list[PatientRow],
    doctors: list[DoctorRow],
    slots: list[SlotRow],
) -> None:
    asha, rahul, meena, _kiran, _sanjay, fatima = patients
    rao, _rao_s, _nair, shetty, menon, iyer = doctors[:6]
    naive_now = to_db_time(now)
    future = [s for s in slots if s.start > naive_now + timedelta(hours=3)]
    await _followup_history(session, now, asha, rao)
    await _past_visit(session, meena, shetty, naive_now - timedelta(days=20))
    taken = _two_upcoming(session, rahul, (menon, iyer), future, naive_now)  # one from the cap
    soon = await _slot_at(session, rao, _round_up(naive_now + timedelta(minutes=60)), slots)
    taken.add(soon.id)
    _book(session, meena, rao, soon, naive_now)  # inside the 2-hour cancel cutoff
    rng = random.Random(42)
    for slot in future:
        if slot.id not in taken and rng.random() < PREBOOK_RATE:
            doctor = next(d for d in doctors if d.id == slot.doctor_id)
            _book(session, fatima, doctor, slot, naive_now)


async def _followup_history(
    session: AsyncSession, now: datetime, patient: PatientRow, doctor: DoctorRow
) -> None:
    past = await _past_visit(session, patient, doctor, to_db_time(now) - timedelta(days=10))
    session.add(
        FollowupGrantRow(
            patient_id=patient.id,
            doctor_id=doctor.id,
            source_appointment_id=past.id,
            valid_until=now.date() + timedelta(days=10),
            created_by=doctor.name,
        )
    )


def _two_upcoming(
    session: AsyncSession,
    patient: PatientRow,
    doctors: tuple[DoctorRow, ...],
    future: list[SlotRow],
    now: datetime,
) -> set[int]:
    taken: set[int] = set()
    for doctor in doctors:
        slot = next(
            s
            for s in future
            if s.doctor_id == doctor.id and s.id not in taken and s.start.date() > now.date()
        )
        taken.add(slot.id)
        _book(session, patient, doctor, slot, now)
    return taken


def _book(
    session: AsyncSession, patient: PatientRow, doctor: DoctorRow, slot: SlotRow, created: datetime
) -> AppointmentRow:
    row = AppointmentRow(
        patient_id=patient.id,
        doctor_id=doctor.id,
        slot_id=slot.id,
        visit_type="new",
        fee=doctor.fee,
        status="booked",
        intake_summary=None,
        session_id=SEED_SESSION,
        created_at=created,
    )
    session.add(row)
    return row


async def _past_visit(
    session: AsyncSession, patient: PatientRow, doctor: DoctorRow, when: datetime
) -> AppointmentRow:
    start = datetime.combine(when.date(), time(10, 0))
    slot = SlotRow(doctor_id=doctor.id, start=start, end=start + timedelta(minutes=SLOT_MINUTES))
    session.add(slot)
    await session.flush()
    row = _book(session, patient, doctor, slot, start - timedelta(days=1))
    await session.flush()
    return row


async def _slot_at(
    session: AsyncSession, doctor: DoctorRow, start: datetime, slots: list[SlotRow]
) -> SlotRow:
    existing = next((s for s in slots if s.doctor_id == doctor.id and s.start == start), None)
    if existing is not None:
        return existing
    slot = SlotRow(doctor_id=doctor.id, start=start, end=start + timedelta(minutes=SLOT_MINUTES))
    session.add(slot)
    await session.flush()
    return slot


def _round_up(value: datetime) -> datetime:
    extra = (-value.minute) % SLOT_MINUTES
    return (value + timedelta(minutes=extra)).replace(second=0, microsecond=0)
