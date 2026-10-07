"""Staff portal services against in-memory fakes (SPEC 17)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from clinic_bot.adapters.clock import FrozenClock
from clinic_bot.config import Settings
from clinic_bot.domain.entities import Appointment
from clinic_bot.domain.enums import AppointmentStatus
from clinic_bot.domain.errors import (
    Conflict,
    Forbidden,
    InvalidInput,
    Locked,
    NotFound,
    Unauthorized,
)
from clinic_bot.domain.policies import LockoutPolicy
from clinic_bot.domain.staff import ClinicDoc, ConsultationNote, EmailAddress
from clinic_bot.services.directory import DoctorDirectory
from clinic_bot.services.staff.accounts import AccountService
from clinic_bot.services.staff.auth import LoginThrottle, StaffAuthService
from clinic_bot.services.staff.clinic import ClinicAdminService
from clinic_bot.services.staff.clinic_docs import ClinicDocService
from clinic_bot.services.staff.consultations import ConsultationService
from clinic_bot.services.staff.passwords import hash_password_sync, verify_password_sync
from clinic_bot.services.staff.records import VisitRecords
from tests.fakes.data import seeded_memory
from tests.fakes.repos import InMemoryUnitOfWorkFactory
from tests.fakes.staff import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    DOCTOR_PASSWORD,
    CountingTables,
    RecordingIndexer,
    make_admin,
    make_doctor,
)

RAO, SHETTY = 1, 4
MEENA = 3


@dataclass
class Portal:
    uow: InMemoryUnitOfWorkFactory
    clock: FrozenClock
    auth: StaffAuthService
    accounts: AccountService
    records: VisitRecords
    consultations: ConsultationService
    clinic: ClinicAdminService
    docs: ClinicDocService
    indexer: RecordingIndexer
    directory: DoctorDirectory

    async def appointment(self, patient_id: int, doctor_id: int, day: date) -> Appointment:
        visits = await self.records.on_day(day)
        return next(
            v.appointment for v in visits if v.patient.id == patient_id and v.doctor.id == doctor_id
        )


@pytest.fixture
async def portal(clock: FrozenClock) -> Portal:
    uow = await seeded_memory(clock)
    directory = DoctorDirectory(uow)
    await directory.reload()
    indexer = RecordingIndexer()
    return Portal(
        uow=uow,
        clock=clock,
        auth=StaffAuthService(uow, clock, LoginThrottle(LockoutPolicy()), 12),
        accounts=AccountService(uow, clock),
        records=VisitRecords(uow, clock, directory),
        consultations=ConsultationService(uow, clock, directory),
        clinic=ClinicAdminService(uow, clock, directory, CountingTables(uow)),
        docs=ClinicDocService(uow, clock, indexer),
        indexer=indexer,
        directory=directory,
    )


def note(days: int | None = None) -> ConsultationNote:
    return ConsultationNote(
        "Examined.", "Viral fever", "Paracetamol 500 mg", days is not None, days
    )


def test_password_hash_round_trip() -> None:
    stored = hash_password_sync("correct horse")
    assert stored.startswith("scrypt$") and "correct horse" not in stored
    assert verify_password_sync("correct horse", stored)
    assert not verify_password_sync("wrong horse", stored)
    assert not verify_password_sync("correct horse", "not-a-hash")


def test_domain_validation() -> None:
    assert EmailAddress.parse("  Dr.Rao@Clinic.TEST ").value == "dr.rao@clinic.test"
    with pytest.raises(InvalidInput):
        EmailAddress.parse("not an email")
    with pytest.raises(InvalidInput):
        ConsultationNote("", "", "", True, 0)
    with pytest.raises(InvalidInput):
        ConsultationNote("", "", "", False, 14)
    with pytest.raises(InvalidInput):
        ClinicDoc("clinic_info.md", "no heading here")
    assert ClinicDoc("clinic_info.md", "# Parking\nFree.").title == "Clinic information"


async def test_login_session_and_logout(portal: Portal) -> None:
    await make_admin(portal.accounts)
    result = await portal.auth.login(" Admin@CityCare.test ", ADMIN_PASSWORD)
    user = await portal.auth.authenticate(result.token)
    assert user.is_admin and user.last_login_at == portal.clock.now()
    assert result.expires_at == portal.clock.now() + timedelta(hours=12)
    await portal.auth.logout(result.token)
    with pytest.raises(Unauthorized):
        await portal.auth.authenticate(result.token)


async def test_wrong_email_and_wrong_password_fail_the_same(portal: Portal) -> None:
    await make_admin(portal.accounts)
    for email, password in ((ADMIN_EMAIL, "wrong-pass"), ("nobody@x.test", ADMIN_PASSWORD)):
        with pytest.raises(Unauthorized):
            await portal.auth.login(email, password)


async def test_login_locks_after_five_failures(portal: Portal) -> None:
    await make_admin(portal.accounts)
    for _ in range(5):
        with pytest.raises(Unauthorized):
            await portal.auth.login(ADMIN_EMAIL, "wrong-pass")
    with pytest.raises(Locked):
        await portal.auth.login(ADMIN_EMAIL, ADMIN_PASSWORD)
    portal.clock.advance(timedelta(minutes=16))
    assert (await portal.auth.login(ADMIN_EMAIL, ADMIN_PASSWORD)).token


async def test_sessions_expire(portal: Portal) -> None:
    await make_admin(portal.accounts)
    token = (await portal.auth.login(ADMIN_EMAIL, ADMIN_PASSWORD)).token
    portal.clock.advance(timedelta(hours=12))
    with pytest.raises(Unauthorized):
        await portal.auth.authenticate(token)


async def test_change_password_keeps_this_session_only(portal: Portal) -> None:
    admin = await make_admin(portal.accounts)
    here = (await portal.auth.login(ADMIN_EMAIL, ADMIN_PASSWORD)).token
    there = (await portal.auth.login(ADMIN_EMAIL, ADMIN_PASSWORD)).token
    with pytest.raises(InvalidInput):
        await portal.auth.change_password(admin, here, "wrong-pass", "new-pass-123")
    await portal.auth.change_password(admin, here, ADMIN_PASSWORD, "new-pass-123")
    assert await portal.auth.authenticate(here)
    with pytest.raises(Unauthorized):
        await portal.auth.authenticate(there)
    assert await portal.auth.login(ADMIN_EMAIL, "new-pass-123")


async def test_doctor_accounts(portal: Portal) -> None:
    admin = await make_admin(portal.accounts)
    doctor = await make_doctor(portal.accounts, RAO, "rao@citycare.test")
    assert doctor.doctor_id == RAO and not doctor.is_admin
    with pytest.raises(Conflict):
        await make_doctor(portal.accounts, SHETTY, "rao@citycare.test")
    with pytest.raises(Conflict):
        await make_doctor(portal.accounts, RAO, "other@citycare.test")
    with pytest.raises(NotFound):
        await make_doctor(portal.accounts, 999, "ghost@citycare.test")
    with pytest.raises(InvalidInput):
        await portal.accounts.create_doctor_account("x@citycare.test", "X Y", "short", SHETTY)
    assert admin.id is not None and doctor.id is not None
    with pytest.raises(Conflict):
        await portal.accounts.update(admin, admin.id, active=False)

    token = (await portal.auth.login("rao@citycare.test", DOCTOR_PASSWORD)).token
    await portal.accounts.update(admin, doctor.id, password="reset-pass-1")
    with pytest.raises(Unauthorized):
        await portal.auth.authenticate(token)
    await portal.accounts.update(admin, doctor.id, active=False)
    with pytest.raises(Unauthorized):
        await portal.auth.login("rao@citycare.test", "reset-pass-1")


async def test_ensure_admin_never_overwrites(portal: Portal) -> None:
    assert await portal.accounts.ensure_admin(ADMIN_EMAIL, "Admin", ADMIN_PASSWORD)
    assert not await portal.accounts.ensure_admin(ADMIN_EMAIL, "Admin", "another-pass")
    assert await portal.auth.login(ADMIN_EMAIL, ADMIN_PASSWORD)


async def test_doctor_lists_only_own_appointments(portal: Portal) -> None:
    today = await portal.records.for_doctor(RAO, "today")
    assert today and {v.doctor.id for v in today} == {RAO}
    assert any(v.patient.id == MEENA for v in today)
    past = await portal.records.for_doctor(RAO, "past")
    assert past and past[0].appointment.slot.start >= past[-1].appointment.slot.start
    appt = await portal.appointment(MEENA, RAO, portal.clock.today())
    assert appt.id is not None
    with pytest.raises(NotFound):
        await portal.records.record(appt.id, SHETTY)


async def test_submit_consultation_creates_and_moves_the_followup_grant(portal: Portal) -> None:
    rao = await make_doctor(portal.accounts, RAO, "rao@citycare.test")
    today = portal.clock.today()
    appt = await portal.appointment(MEENA, RAO, today)
    assert appt.id is not None

    await portal.consultations.submit(rao, appt.id, note(14))
    record = await portal.records.record(appt.id, RAO)
    assert record.visit.appointment.status is AppointmentStatus.COMPLETED
    assert record.consultation is not None and record.consultation.note.diagnosis == "Viral fever"
    assert record.followup_valid_until == today + timedelta(days=14)
    async with portal.uow() as uow:
        grant = await uow.followups.active(MEENA, RAO, today)
    assert grant is not None and grant.created_by == "Dr. Rao"
    assert grant.source_appointment_id == appt.id

    await portal.consultations.submit(rao, appt.id, note(7))
    record = await portal.records.record(appt.id, RAO)
    assert record.followup_valid_until == today + timedelta(days=7)
    assert record.consultation and record.consultation.followup_grant_id == grant.id

    await portal.consultations.submit(rao, appt.id, note())
    async with portal.uow() as uow:
        assert await uow.followups.get(grant.id) is None


async def test_a_used_grant_is_left_alone(portal: Portal) -> None:
    rao = await make_doctor(portal.accounts, RAO, "rao@citycare.test")
    appt = await portal.appointment(MEENA, RAO, portal.clock.today())
    assert appt.id is not None
    await portal.consultations.submit(rao, appt.id, note(14))
    async with portal.uow(write=True) as uow:
        grant = await uow.followups.active(MEENA, RAO, portal.clock.today())
        assert grant is not None
        grant.mark_used(999)
        await uow.followups.save(grant)
        await uow.commit()
    await portal.consultations.submit(rao, appt.id, note())
    async with portal.uow() as uow:
        assert await uow.followups.get(grant.id) is not None


async def test_only_the_treating_doctor_records_past_or_today_visits(portal: Portal) -> None:
    admin = await make_admin(portal.accounts)
    rao = await make_doctor(portal.accounts, RAO, "rao@citycare.test")
    shetty = await make_doctor(portal.accounts, SHETTY, "shetty@citycare.test")
    appt = await portal.appointment(MEENA, RAO, portal.clock.today())
    assert appt.id is not None
    with pytest.raises(Forbidden):
        await portal.consultations.submit(admin, appt.id, note())
    with pytest.raises(NotFound):
        await portal.consultations.submit(shetty, appt.id, note())
    later = (await portal.records.for_doctor(RAO, "upcoming"))[0].appointment
    assert later.id is not None
    with pytest.raises(Conflict):
        await portal.consultations.submit(rao, later.id, note())
    with pytest.raises(Conflict):
        await portal.consultations.update_visit(rao, later.id, status=AppointmentStatus.NO_SHOW)


async def test_update_visit_keeps_the_bots_answers(portal: Portal) -> None:
    rao = await make_doctor(portal.accounts, RAO, "rao@citycare.test")
    appt = await portal.appointment(MEENA, RAO, portal.clock.today())
    assert appt.id is not None
    await portal.consultations.update_visit(
        rao, appt.id, status=AppointmentStatus.NO_SHOW, chief_complaint=" Cough ", severity=4
    )
    record = await portal.records.record(appt.id, RAO)
    updated = record.visit.appointment
    assert updated.status is AppointmentStatus.NO_SHOW
    assert updated.intake is not None and updated.intake.chief_complaint == "Cough"
    assert updated.intake.severity == 4 and updated.intake.duration is None
    with pytest.raises(InvalidInput):
        await portal.consultations.update_visit(rao, appt.id, status=AppointmentStatus.CANCELLED)


async def test_history_shows_other_consultations(portal: Portal) -> None:
    shetty = await make_doctor(portal.accounts, SHETTY, "shetty@citycare.test")
    earlier = (await portal.records.for_doctor(SHETTY, "past"))[0].appointment
    today = await portal.appointment(MEENA, RAO, portal.clock.today())
    assert earlier.id is not None and today.id is not None and earlier.patient_id == MEENA
    await portal.consultations.submit(shetty, earlier.id, note())
    record = await portal.records.record(today.id, RAO)
    assert [(h.appointment_id, h.doctor_name) for h in record.history] == [
        (earlier.id, "Dr. Kavya Shetty")
    ]
    assert record.consultation is None and record.can_record


async def test_admin_edits_doctor_and_the_directory_reloads(portal: Portal) -> None:
    entry = await portal.clinic.update_doctor(
        RAO, name="Dr. Rao K", bio="Physician.", fee_rupees=700, followup_fee_rupees=350
    )
    assert entry.doctor.fee.paise == 70_000
    assert portal.directory.get(RAO).name == "Dr. Rao K"
    with pytest.raises(InvalidInput):
        await portal.clinic.update_doctor(
            RAO, name="Dr. Rao", bio="", fee_rupees=-1, followup_fee_rupees=0
        )


async def test_closures(portal: Portal) -> None:
    today = portal.clock.today()
    before = await portal.clinic.closures()
    added = await portal.clinic.add_closure(today + timedelta(days=2), "Festival")
    assert added.booked_appointments >= 0 and added.closure.id is not None
    with pytest.raises(Conflict):
        await portal.clinic.add_closure(today + timedelta(days=2), "Again")
    with pytest.raises(InvalidInput):
        await portal.clinic.add_closure(today - timedelta(days=1), "Past")
    assert len(await portal.clinic.closures()) == len(before) + 1
    await portal.clinic.delete_closure(added.closure.id)
    with pytest.raises(NotFound):
        await portal.clinic.delete_closure(added.closure.id)


async def test_overview_counts(portal: Portal) -> None:
    o = await portal.clinic.overview()
    assert o.counts["patients"] == 6 and o.counts["doctors"] == 8
    assert o.appointments_today >= 1 and o.upcoming_appointments > o.appointments_today


async def test_saving_a_clinic_doc_reindexes(portal: Portal) -> None:
    admin = await make_admin(portal.accounts)
    saved = await portal.docs.save("clinic_info.md", "# Parking\r\nValet parking.", admin)
    assert saved.content == "# Parking\nValet parking." and saved.updated_by == "Clinic admin"
    assert portal.indexer.rebuilt == [{"clinic_info.md": "# Parking\nValet parking."}]
    with pytest.raises(NotFound):
        await portal.docs.save("specialty_guide.md", "# X\ny", admin)
    with pytest.raises(InvalidInput):
        await portal.docs.save("clinic_info.md", "no heading", admin)


def test_origin_lists_parse_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STAFF_ORIGINS", "http://a.test, http://b.test")
    monkeypatch.setenv("ALLOWED_ORIGINS", '["http://c.test"]')
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.staff_origins == ["http://a.test", "http://b.test"]
    assert s.allowed_origins == ["http://c.test"]
