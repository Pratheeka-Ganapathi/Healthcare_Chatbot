"""Startup seeding on PostgreSQL: an existing database is kept, and the slot window moves."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import ColumnElement, func, select

from clinic_bot.adapters.clock import FrozenClock
from clinic_bot.adapters.db.engine import create_engine
from clinic_bot.adapters.db.orm import Base, PatientRow, SlotRow
from clinic_bot.domain.enums import Sex
from clinic_bot.domain.values import DateOfBirth, PersonName, PhoneNumber
from clinic_bot.seed.seeder import Seeder
from tests.conftest import TEST_DATABASE_URL
from tests.fakes.data import seeded_sql


async def _count(table: type[Base], *where: ColumnElement[bool]) -> int:
    engine = create_engine(TEST_DATABASE_URL, pooled=False)
    try:
        async with engine.connect() as conn:
            stmt = select(func.count()).select_from(table).where(*where)
            return int((await conn.execute(stmt)).scalar_one())
    finally:
        await engine.dispose()


async def test_startup_keeps_existing_data(clock: FrozenClock) -> None:
    uow = await seeded_sql(clock)
    async with uow(write=True) as u:
        name, dob = PersonName("Priya Sharma"), DateOfBirth(date(1988, 4, 12))
        await u.patients.add(name, PhoneNumber("9888800001"), dob, Sex.FEMALE, clock.now())
        await u.commit()
    engine = create_engine(TEST_DATABASE_URL, pooled=False)
    await Seeder(engine, clock).ensure_seeded()
    await engine.dispose()
    assert await _count(PatientRow, PatientRow.phone == "9888800001") == 1


async def test_startup_tops_up_slots_as_days_pass(clock: FrozenClock) -> None:
    await seeded_sql(clock)
    later = FrozenClock(clock.now() + timedelta(days=10))
    new_day = later.now().date() + timedelta(days=1)
    day_start = SlotRow.start >= new_day
    assert await _count(SlotRow, day_start) == 0
    before = await _count(SlotRow)
    engine = create_engine(TEST_DATABASE_URL, pooled=False)
    await Seeder(engine, later).ensure_seeded()
    await Seeder(engine, later).ensure_seeded()  # idempotent
    await engine.dispose()
    assert await _count(SlotRow, day_start) > 0 and await _count(SlotRow) > before
