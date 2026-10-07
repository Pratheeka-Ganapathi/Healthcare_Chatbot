"""Seeded demo data, shared by PostgreSQL-backed and in-memory tests."""

from __future__ import annotations

import copy
from datetime import date, datetime

from sqlalchemy import select

from clinic_bot.adapters.clock import FrozenClock
from clinic_bot.adapters.db import mappers
from clinic_bot.adapters.db.engine import create_engine, session_factory
from clinic_bot.adapters.db.orm import (
    AppointmentRow,
    ClosureRow,
    FollowupGrantRow,
    PatientRow,
    SlotRow,
)
from clinic_bot.adapters.db.uow import SqlUnitOfWorkFactory
from clinic_bot.domain.entities import Closure
from clinic_bot.seed.seeder import Seeder
from tests.conftest import TEST_DATABASE_URL
from tests.fakes.repos import InMemoryUnitOfWorkFactory, Store

_MEMORY_SEEDS: dict[datetime, Store] = {}


async def seeded_sql(clock: FrozenClock) -> SqlUnitOfWorkFactory:
    """A freshly reseeded test database. Unpooled, so nothing is left open."""
    engine = create_engine(TEST_DATABASE_URL, pooled=False)
    await Seeder(engine, clock).reseed()
    return SqlUnitOfWorkFactory(session_factory(engine), clock)


async def seeded_memory(clock: FrozenClock) -> InMemoryUnitOfWorkFactory:
    """Same rows as the SQL seed, in memory. Seeded once per clock, then copied."""
    now = clock.now()
    if now not in _MEMORY_SEEDS:
        _MEMORY_SEEDS[now] = await _copy_seed(clock)
    return InMemoryUnitOfWorkFactory(copy.deepcopy(_MEMORY_SEEDS[now]))


async def _copy_seed(clock: FrozenClock) -> Store:
    sql = await seeded_sql(clock)
    store = Store()
    async with sql() as uow:
        session = uow._session
        assert session is not None
        for row in await session.scalars(select(PatientRow)):
            store.patients[row.id] = mappers.patient(row)
        for d in await uow.doctors.all():
            store.doctors[d.id] = d
        slot_rows = {r.id: r for r in await session.scalars(select(SlotRow))}
        for row in slot_rows.values():
            store.slots[row.id] = mappers.slot(row)
        for row in await session.scalars(select(ClosureRow)):
            store.closures[row.date] = Closure(row.date, row.reason, row.id)
        for row in await session.scalars(select(AppointmentRow)):
            store.appointments[row.id] = (
                mappers.appointment(row, slot_rows[row.slot_id]),
                row.session_id,
            )
        for row in await session.scalars(select(FollowupGrantRow)):
            store.grants[row.id] = mappers.grant(row)
    return store


def at(clock: FrozenClock, day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=clock.now().tzinfo)
