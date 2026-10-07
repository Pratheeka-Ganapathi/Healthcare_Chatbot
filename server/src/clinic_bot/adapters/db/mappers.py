"""ORM rows ↔ domain objects. ORM classes never leave adapters/db."""

from __future__ import annotations

from datetime import datetime

from clinic_bot.adapters.clock import IST
from clinic_bot.adapters.db.orm import (
    AppointmentRow,
    DoctorRow,
    FollowupGrantRow,
    PatientRow,
    SlotRow,
)
from clinic_bot.domain.entities import (
    Appointment,
    Doctor,
    FollowupGrant,
    IntakeSummary,
    Patient,
    Slot,
)
from clinic_bot.domain.enums import AppointmentStatus, Sex, Specialty, VisitType
from clinic_bot.domain.values import DateOfBirth, Money, PhoneNumber, TimeWindow


def to_db_time(value: datetime) -> datetime:
    """Aware → naive IST for storage."""
    return value.astimezone(IST).replace(tzinfo=None)


def from_db_time(value: datetime) -> datetime:
    return value.replace(tzinfo=IST)


def patient(row: PatientRow) -> Patient:
    return Patient(row.id, row.name, PhoneNumber(row.phone), DateOfBirth(row.dob), Sex(row.sex))


def doctor(row: DoctorRow) -> Doctor:
    days = tuple(int(d) for d in row.consulting_days.split(",") if d)
    return Doctor(
        id=row.id,
        name=row.name,
        specialty=Specialty(row.specialty),
        bio=row.bio,
        consulting_days=days,
        hours=row.hours,
        fee=Money(row.fee),
        followup_fee=Money(row.followup_fee),
    )


def slot(row: SlotRow) -> Slot:
    return Slot(row.id, row.doctor_id, TimeWindow(from_db_time(row.start), from_db_time(row.end)))


def appointment(row: AppointmentRow, slot_row: SlotRow) -> Appointment:
    return Appointment(
        id=row.id,
        patient_id=row.patient_id,
        doctor_id=row.doctor_id,
        slot=slot(slot_row),
        visit_type=VisitType(row.visit_type),
        fee=Money(row.fee),
        status=AppointmentStatus(row.status),
        intake=IntakeSummary.from_dict(row.intake_summary) if row.intake_summary else None,
        followup_grant_id=row.followup_grant_id,
        cancelled_at=from_db_time(row.cancelled_at) if row.cancelled_at else None,
    )


def grant(row: FollowupGrantRow) -> FollowupGrant:
    return FollowupGrant(
        id=row.id,
        patient_id=row.patient_id,
        doctor_id=row.doctor_id,
        source_appointment_id=row.source_appointment_id,
        valid_until=row.valid_until,
        created_by=row.created_by,
        used_appointment_id=row.used_appointment_id,
    )
