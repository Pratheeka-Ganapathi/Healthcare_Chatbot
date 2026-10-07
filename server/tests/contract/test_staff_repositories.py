"""Staff portal repository contract: in-memory fakes and PostgreSQL behave the same."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta

import pytest

from clinic_bot.adapters.clock import FrozenClock
from clinic_bot.adapters.db.browser import SqlTableBrowser
from clinic_bot.adapters.db.uow import SqlUnitOfWorkFactory
from clinic_bot.domain.entities import Closure, IntakeSummary
from clinic_bot.domain.enums import AppointmentStatus, StaffRole
from clinic_bot.domain.errors import Conflict, NotFound
from clinic_bot.domain.staff import (
    ClinicDoc,
    Consultation,
    ConsultationNote,
    EmailAddress,
    StaffSession,
    StaffUser,
)
from clinic_bot.domain.values import Money
from clinic_bot.ports.unit_of_work import UnitOfWorkFactory
from tests.fakes.data import seeded_memory, seeded_sql

RAO = 1


@pytest.fixture(params=["memory", "sql"])
async def uow(request: pytest.FixtureRequest, clock: FrozenClock) -> UnitOfWorkFactory:
    if request.param == "memory":
        return await seeded_memory(clock)
    return await seeded_sql(clock)


def _user(clock: FrozenClock, email: str, doctor_id: int | None = None) -> StaffUser:
    role = StaffRole.DOCTOR if doctor_id else StaffRole.ADMIN
    return StaffUser(
        None, EmailAddress(email), "Some One", role, doctor_id, "scrypt$x", True, clock.now()
    )


def _day(clock: FrozenClock, d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=clock.now().tzinfo)


async def test_staff_users(uow: UnitOfWorkFactory, clock: FrozenClock) -> None:
    async with uow(write=True) as u:
        admin = await u.staff_users.add(_user(clock, "admin@x.test"))
        doc = await u.staff_users.add(_user(clock, "rao@x.test", RAO))
        with pytest.raises(Conflict):
            await u.staff_users.add(_user(clock, "admin@x.test"))
        with pytest.raises(Conflict):
            await u.staff_users.add(_user(clock, "rao2@x.test", RAO))
        await u.commit()
    assert admin.id and doc.id
    async with uow(write=True) as u:
        assert await u.staff_users.by_email(EmailAddress("rao@x.test")) == doc
        assert await u.staff_users.by_doctor(RAO) == doc
        assert [x.email.value for x in await u.staff_users.all()] == ["admin@x.test", "rao@x.test"]
        later = clock.now() + timedelta(hours=1)
        await u.staff_users.save(replace(doc, name="Dr R", active=False, last_login_at=later))
        await u.commit()
    async with uow() as u:
        saved = await u.staff_users.get(doc.id)
    assert saved is not None and saved.name == "Dr R" and not saved.active
    assert saved.last_login_at == later


async def test_staff_sessions(uow: UnitOfWorkFactory, clock: FrozenClock) -> None:
    now = clock.now()
    async with uow(write=True) as u:
        user = await u.staff_users.add(_user(clock, "admin@x.test"))
        assert user.id
        for token, hours in (("a" * 64, 12), ("b" * 64, 12), ("c" * 64, -1)):
            await u.staff_sessions.add(StaffSession.start(token, user.id, now, hours))
        await u.commit()
    async with uow(write=True) as u:
        assert (await u.staff_sessions.get("a" * 64)) == StaffSession.start(
            "a" * 64, user.id, now, 12
        )
        await u.staff_sessions.purge_expired(now)
        await u.staff_sessions.delete_for_user(user.id, keep="a" * 64)
        await u.commit()
    async with uow(write=True) as u:
        assert await u.staff_sessions.get("a" * 64) is not None
        assert await u.staff_sessions.get("b" * 64) is None
        assert await u.staff_sessions.get("c" * 64) is None
        await u.staff_sessions.delete("a" * 64)
        await u.commit()
    async with uow() as u:
        assert await u.staff_sessions.get("a" * 64) is None


async def test_consultations(uow: UnitOfWorkFactory, clock: FrozenClock) -> None:
    today = clock.now().date()
    async with uow(write=True) as u:
        user = await u.staff_users.add(_user(clock, "rao@x.test", RAO))
        past = await u.appointments.between(
            _day(clock, today - timedelta(days=30)), _day(clock, today)
        )
        first, second = sorted(past, key=lambda a: a.slot.start)[:2]
        assert user.id and first.id and second.id
        note = ConsultationNote("n", "d", "m", True, 14)
        made = []
        for appt in (first, second):
            c = Consultation(
                None,
                appt.id,
                appt.doctor_id,
                first.patient_id,
                note,
                7,
                user.id,
                clock.now(),
                clock.now(),
            )
            made.append(await u.consultations.add(c))
        await u.commit()
    async with uow(write=True) as u:
        with pytest.raises(Conflict):
            await u.consultations.add(made[0])
    async with uow(write=True) as u:
        assert await u.consultations.for_appointment(first.id) == made[0]
        newest = [c.appointment_id for c in await u.consultations.for_patient(first.patient_id)]
        assert newest == [second.id, first.id]
        assert await u.consultations.with_consultation({first.id, 99_999}) == {first.id}
        revised = made[0].revised(
            ConsultationNote("x", "y", "z", False, None),
            None,
            user.id,
            clock.now() + timedelta(minutes=5),
        )
        await u.consultations.save(revised)
        await u.commit()
    async with uow() as u:
        assert await u.consultations.for_appointment(first.id) == revised


async def test_clinic_docs(uow: UnitOfWorkFactory, clock: FrozenClock) -> None:
    doc = ClinicDoc("clinic_info.md", "# A\nb", clock.now(), "Admin")
    async with uow(write=True) as u:
        await u.clinic_docs.save(ClinicDoc("clinic_info.md", "# Old\nx"))
        await u.clinic_docs.save(doc)
        await u.commit()
    async with uow() as u:
        assert await u.clinic_docs.get("clinic_info.md") == doc
        assert [d.name for d in await u.clinic_docs.all()] == ["clinic_info.md"]
        assert await u.clinic_docs.get("services.md") is None


async def test_closures_admin(uow: UnitOfWorkFactory, clock: FrozenClock) -> None:
    today = clock.now().date()
    async with uow(write=True) as u:
        seeded = await u.closures.from_day(today)
        assert len(seeded) == 1 and seeded[0].id is not None
        added = await u.closures.add(Closure(today + timedelta(days=5), "Festival"))
        with pytest.raises(Conflict):
            await u.closures.add(Closure(today + timedelta(days=5), "Again"))
    async with uow(write=True) as u:
        added = await u.closures.add(Closure(today + timedelta(days=5), "Festival"))
        await u.commit()
    assert added.id is not None
    async with uow(write=True) as u:
        assert [c.reason for c in await u.closures.from_day(today)][-1] == "Festival"
        assert await u.closures.on(today + timedelta(days=5)) == added
        await u.closures.delete(added.id)
        with pytest.raises(NotFound):
            await u.closures.delete(added.id)
        await u.commit()


async def test_appointments_between_and_intake_save(
    uow: UnitOfWorkFactory, clock: FrozenClock
) -> None:
    today = clock.now().date()
    start, end = _day(clock, today), _day(clock, today + timedelta(days=1))
    async with uow(write=True) as u:
        rao_today = await u.appointments.between(start, end, doctor_id=RAO)
        everyone = await u.appointments.between(start, end)
        assert rao_today and all(a.doctor_id == RAO for a in rao_today)
        assert len(everyone) >= len(rao_today)
        starts = [a.slot.start for a in everyone]
        assert starts == sorted(starts)
        newest = await u.appointments.between(start, end, newest_first=True)
        assert [a.slot.start for a in newest] == sorted(starts, reverse=True)
        appt = rao_today[0]
        appt.intake = IntakeSummary("Cough", "3 days", 4)
        appt.status = AppointmentStatus.COMPLETED
        await u.appointments.save(appt)
        await u.commit()
    async with uow() as u:
        assert appt.id is not None
        saved = await u.appointments.get(appt.id)
    assert saved is not None and saved.status is AppointmentStatus.COMPLETED
    assert saved.intake == IntakeSummary("Cough", "3 days", 4)


async def test_followup_add_move_delete(uow: UnitOfWorkFactory, clock: FrozenClock) -> None:
    today = clock.now().date()
    async with uow(write=True) as u:
        grant = await u.followups.add(3, RAO, 1, today + timedelta(days=14), "Dr. Rao")
        grant.valid_until = today + timedelta(days=7)
        await u.followups.save(grant)
        await u.commit()
    async with uow(write=True) as u:
        assert (await u.followups.active(3, RAO, today)) == grant
        await u.followups.delete(grant.id)
        await u.commit()
    async with uow() as u:
        assert await u.followups.get(grant.id) is None


async def test_patients_many_and_doctor_save(uow: UnitOfWorkFactory) -> None:
    async with uow(write=True) as u:
        found = await u.patients.many({1, 3, 999})
        assert sorted(found) == [1, 3] and found[1].name == "Asha Kumar"
        assert await u.patients.many(set()) == {}
        rao = await u.doctors.require(RAO)
        await u.doctors.save(replace(rao, name="Dr. Rao K", fee=Money.rupees(700)))
        await u.commit()
    async with uow() as u:
        saved = await u.doctors.require(RAO)
    assert saved.name == "Dr. Rao K" and saved.fee == Money.rupees(700)
    assert saved.consulting_days == rao.consulting_days


async def test_table_browser_hides_secrets(clock: FrozenClock) -> None:
    sql = await seeded_sql(clock)
    async with sql(write=True) as u:
        await u.staff_users.add(_user(clock, "admin@x.test"))
        await u.commit()
    assert isinstance(sql, SqlUnitOfWorkFactory)
    browser = SqlTableBrowser(sql._factory)
    names = {t.name: t.row_count for t in await browser.tables()}
    assert names["patients"] == 6 and "staff_sessions" not in names
    page = await browser.page("staff_users", 0, 50)
    assert "password_hash" not in page.columns and page.total == 1
    assert page.rows[0][page.columns.index("email")] == "admin@x.test"
    slots = await browser.page("slots", 10, 5)
    assert len(slots.rows) == 5 and slots.offset == 10 and isinstance(slots.rows[0][2], str)
    with pytest.raises(NotFound):
        await browser.page("staff_sessions", 0, 10)
