"""Response bodies shared by doctor and admin screens (SPEC 17.5). Money is whole rupees."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel

from clinic_bot.domain.entities import Appointment, IntakeSummary, Patient
from clinic_bot.domain.staff import Consultation, StaffUser
from clinic_bot.services.directory import DoctorDirectory
from clinic_bot.services.scheduling import day_label, time_label
from clinic_bot.services.staff.records import Visit, VisitRecord

Status = Literal["booked", "cancelled", "completed", "no_show"]


class StaffUserOut(BaseModel):
    id: int
    email: str
    name: str
    role: Literal["admin", "doctor"]
    doctor_id: int | None
    doctor_name: str | None
    active: bool
    created_at: datetime
    last_login_at: datetime | None

    @classmethod
    def of(cls, user: StaffUser, directory: DoctorDirectory) -> Self:
        assert user.id is not None
        doctor = directory.get(user.doctor_id).name if user.doctor_id else None
        return cls(
            id=user.id,
            email=user.email.value,
            name=user.name,
            role=user.role.value,
            doctor_id=user.doctor_id,
            doctor_name=doctor,
            active=user.active,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )


class LoginOut(BaseModel):
    token: str
    expires_at: datetime
    user: StaffUserOut


class PatientRefOut(BaseModel):
    id: int
    name: str
    age: int
    sex: Literal["female", "male", "other"]


class PatientOut(PatientRefOut):
    phone: str
    dob: date

    @classmethod
    def of(cls, patient: Patient, age: int) -> Self:
        return cls(
            id=patient.id,
            name=patient.name,
            age=age,
            sex=patient.sex.value,
            phone=patient.phone.digits,
            dob=patient.dob.value,
        )


class AppointmentSummaryOut(BaseModel):
    id: int
    start: datetime
    end: datetime
    date_label: str
    time_label: str
    doctor_id: int
    doctor_name: str
    patient: PatientRefOut
    visit_type: Literal["new", "followup"]
    status: Status
    chief_complaint: str | None
    has_consultation: bool

    @staticmethod
    def fields_of(visit: Visit) -> dict[str, object]:
        a: Appointment = visit.appointment
        assert a.id is not None
        return {
            "id": a.id,
            "start": a.slot.start,
            "end": a.slot.window.end,
            "date_label": day_label(a.slot.day),
            "time_label": time_label(a.slot),
            "doctor_id": a.doctor_id,
            "doctor_name": visit.doctor.name,
            "visit_type": a.visit_type.value,
            "status": a.status.value,
            "chief_complaint": a.intake.chief_complaint if a.intake else None,
            "has_consultation": visit.has_consultation,
        }

    @classmethod
    def of(cls, visit: Visit) -> Self:
        p = visit.patient
        patient = PatientRefOut(id=p.id, name=p.name, age=visit.patient_age, sex=p.sex.value)
        return cls.model_validate({**cls.fields_of(visit), "patient": patient})


class IntakeAnswerOut(BaseModel):
    q: str
    a: str


class IntakeOut(BaseModel):
    chief_complaint: str
    duration: str | None
    severity: int | None
    answers: list[IntakeAnswerOut]
    red_flags_checked: list[str]

    @classmethod
    def of(cls, intake: IntakeSummary) -> Self:
        return cls(
            chief_complaint=intake.chief_complaint,
            duration=intake.duration,
            severity=intake.severity,
            answers=[IntakeAnswerOut(q=a.q, a=a.a) for a in intake.answers],
            red_flags_checked=list(intake.red_flags_checked),
        )


class ConsultationOut(BaseModel):
    notes: str
    diagnosis: str
    medication: str
    followup_required: bool
    followup_in_days: int | None
    followup_valid_until: date | None
    submitted_by: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, c: Consultation, by: str | None, valid_until: date | None) -> Self:
        n = c.note
        return cls(
            notes=n.notes,
            diagnosis=n.diagnosis,
            medication=n.medication,
            followup_required=n.followup_required,
            followup_in_days=n.followup_in_days,
            followup_valid_until=valid_until,
            submitted_by=by or "",
            created_at=c.created_at,
            updated_at=c.updated_at,
        )


class ChatSummaryOut(BaseModel):
    id: int
    summary: str
    created_at: datetime


class HistoryItemOut(BaseModel):
    appointment_id: int
    date_label: str
    doctor_name: str
    diagnosis: str
    notes: str
    medication: str
    followup_required: bool


class AppointmentDetailOut(AppointmentSummaryOut):
    fee_rupees: int
    patient: PatientOut
    intake: IntakeOut | None
    consultation: ConsultationOut | None
    chat_summaries: list[ChatSummaryOut]
    history: list[HistoryItemOut]
    can_record: bool

    @classmethod
    def of_record(cls, r: VisitRecord) -> Self:
        a, c = r.visit.appointment, r.consultation
        return cls.model_validate(
            {
                **cls.fields_of(r.visit),
                "fee_rupees": a.fee.paise // 100,
                "patient": PatientOut.of(r.visit.patient, r.visit.patient_age),
                "intake": IntakeOut.of(a.intake) if a.intake else None,
                "consultation": (
                    ConsultationOut.of(c, r.consultation_by, r.followup_valid_until) if c else None
                ),
                "chat_summaries": [
                    ChatSummaryOut(id=s.id or 0, summary=s.summary, created_at=s.created_at)
                    for s in r.chat_summaries
                ],
                "history": [
                    HistoryItemOut(
                        appointment_id=h.appointment_id,
                        date_label=day_label(h.day),
                        doctor_name=h.doctor_name,
                        diagnosis=h.consultation.note.diagnosis,
                        notes=h.consultation.note.notes,
                        medication=h.consultation.note.medication,
                        followup_required=h.consultation.note.followup_required,
                    )
                    for h in r.history
                ],
                "can_record": r.can_record,
            }
        )
