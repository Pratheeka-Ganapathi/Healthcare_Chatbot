"""Admin screens: overview, appointments, doctors, accounts, clinic docs, closures,
database (SPEC 17.3)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query, status

from clinic_bot.api.staff.admin_views import (
    ClinicDocOut,
    ClosureOut,
    DoctorOut,
    OverviewOut,
    TableInfoOut,
    TablePageOut,
)
from clinic_bot.api.staff.bodies import AccountIn, AccountPatchIn, ClosureIn, DocIn, DoctorIn
from clinic_bot.api.staff.deps import Admin, Staff
from clinic_bot.api.staff.views import AppointmentDetailOut, AppointmentSummaryOut, StaffUserOut

router = APIRouter(prefix="/admin", tags=["staff: admin"])


@router.get("/overview")
async def overview(_: Admin, staff: Staff) -> OverviewOut:
    o = await staff.clinic.overview()
    return OverviewOut(
        **o.counts,
        appointments_today=o.appointments_today,
        upcoming_appointments=o.upcoming_appointments,
    )


@router.get("/appointments")
async def appointments(
    _: Admin, staff: Staff, day: date | None = None
) -> list[AppointmentSummaryOut]:
    visits = await staff.records.on_day(day or staff.clock.today())
    return [AppointmentSummaryOut.of(v) for v in visits]


@router.get("/appointments/{appointment_id}")
async def appointment(appointment_id: int, _: Admin, staff: Staff) -> AppointmentDetailOut:
    return AppointmentDetailOut.of_record(await staff.records.record(appointment_id, None))


@router.get("/doctors")
async def doctors(_: Admin, staff: Staff) -> list[DoctorOut]:
    return [DoctorOut.of(d) for d in await staff.clinic.doctors()]


@router.put("/doctors/{doctor_id}")
async def update_doctor(doctor_id: int, body: DoctorIn, _: Admin, staff: Staff) -> DoctorOut:
    entry = await staff.clinic.update_doctor(
        doctor_id,
        name=body.name,
        bio=body.bio,
        fee_rupees=body.fee_rupees,
        followup_fee_rupees=body.followup_fee_rupees,
    )
    return DoctorOut.of(entry)


@router.get("/accounts")
async def accounts(_: Admin, staff: Staff) -> list[StaffUserOut]:
    return [StaffUserOut.of(u, staff.directory) for u in await staff.accounts.all()]


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
async def create_account(body: AccountIn, _: Admin, staff: Staff) -> StaffUserOut:
    user = await staff.accounts.create_doctor_account(
        body.email, body.name, body.password, body.doctor_id
    )
    return StaffUserOut.of(user, staff.directory)


@router.patch("/accounts/{user_id}")
async def update_account(
    user_id: int, body: AccountPatchIn, who: Admin, staff: Staff
) -> StaffUserOut:
    user = await staff.accounts.update(
        who.user, user_id, name=body.name, active=body.active, password=body.password
    )
    return StaffUserOut.of(user, staff.directory)


@router.get("/clinic-docs")
async def clinic_docs(_: Admin, staff: Staff) -> list[ClinicDocOut]:
    return [ClinicDocOut.of(d) for d in await staff.docs.all()]


@router.put("/clinic-docs/{name}")
async def save_clinic_doc(name: str, body: DocIn, who: Admin, staff: Staff) -> ClinicDocOut:
    return ClinicDocOut.of(await staff.docs.save(name, body.content, who.user))


@router.get("/closures")
async def closures(_: Admin, staff: Staff) -> list[ClosureOut]:
    return [ClosureOut.of(c) for c in await staff.clinic.closures()]


@router.post("/closures", status_code=status.HTTP_201_CREATED)
async def add_closure(body: ClosureIn, _: Admin, staff: Staff) -> ClosureOut:
    return ClosureOut.of(await staff.clinic.add_closure(body.date, body.reason))


@router.delete("/closures/{closure_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_closure(closure_id: int, _: Admin, staff: Staff) -> None:
    await staff.clinic.delete_closure(closure_id)


@router.get("/tables")
async def tables(_: Admin, staff: Staff) -> list[TableInfoOut]:
    return [TableInfoOut(name=t.name, row_count=t.row_count) for t in await staff.tables.tables()]


@router.get("/tables/{name}")
async def table_page(
    name: str,
    _: Admin,
    staff: Staff,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> TablePageOut:
    return TablePageOut.of(await staff.tables.page(name, offset, limit))
