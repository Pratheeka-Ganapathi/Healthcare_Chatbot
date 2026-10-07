"""The doctor's appointments, visit details and consultation form (SPEC 17.2)."""

from __future__ import annotations

from fastapi import APIRouter

from clinic_bot.api.staff.bodies import ConsultationIn, VisitPatchIn
from clinic_bot.api.staff.deps import DoctorCaller, Staff
from clinic_bot.api.staff.views import AppointmentDetailOut, AppointmentSummaryOut
from clinic_bot.domain.enums import AppointmentStatus
from clinic_bot.domain.staff import ConsultationNote
from clinic_bot.services.staff.records import Scope

router = APIRouter(prefix="/doctor", tags=["staff: doctor"])


@router.get("/appointments")
async def appointments(
    who: DoctorCaller, staff: Staff, scope: Scope = "today"
) -> list[AppointmentSummaryOut]:
    assert who.user.doctor_id is not None
    visits = await staff.records.for_doctor(who.user.doctor_id, scope)
    return [AppointmentSummaryOut.of(v) for v in visits]


@router.get("/appointments/{appointment_id}")
async def appointment(appointment_id: int, who: DoctorCaller, staff: Staff) -> AppointmentDetailOut:
    record = await staff.records.record(appointment_id, who.user.doctor_id)
    return AppointmentDetailOut.of_record(record)


@router.patch("/appointments/{appointment_id}")
async def update_appointment(
    appointment_id: int, body: VisitPatchIn, who: DoctorCaller, staff: Staff
) -> AppointmentDetailOut:
    intake = body.intake
    await staff.consultations.update_visit(
        who.user,
        appointment_id,
        status=AppointmentStatus(body.status) if body.status else None,
        chief_complaint=intake.chief_complaint if intake else None,
        duration=intake.duration if intake else None,
        severity=intake.severity if intake else None,
    )
    return await appointment(appointment_id, who, staff)


@router.put("/appointments/{appointment_id}/consultation")
async def submit_consultation(
    appointment_id: int, body: ConsultationIn, who: DoctorCaller, staff: Staff
) -> AppointmentDetailOut:
    note = ConsultationNote(
        notes=body.notes.strip(),
        diagnosis=body.diagnosis.strip(),
        medication=body.medication.strip(),
        followup_required=body.followup_required,
        followup_in_days=body.followup_in_days if body.followup_required else None,
    )
    await staff.consultations.submit(who.user, appointment_id, note)
    return await appointment(appointment_id, who, staff)
